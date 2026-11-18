// Read-only verifier for WetMap's existing Angular/default release policy.
// No publisher, Git writes, HTTP client, token handling or arbitrary glob rules.
import { execFileSync } from "node:child_process";
import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import angular from "conventional-changelog-angular";
import { CommitParser } from "conventional-commits-parser";
import { filterRevertedCommitsSync } from "conventional-commits-filter";
import semver from "semver";

const shaPattern = /^[a-f0-9]{40}$/;
const maximumBytes = 2 * 1024 * 1024;
const expectedPolicy = {
  branches: ["main"],
  tagFormat: "v${version}",
  plugins: [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    "@semantic-release/github",
  ],
};
const ranks = { patch: 1, minor: 2, major: 3 };
const typeRules = {
  feat: "minor",
  fix: "patch",
  perf: "patch",
  FEAT: "minor",
  FIX: "patch",
};

export class PlanError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

// Same parser/preset/filter versions as the audited 25.0.9 reference tree.
// Its default rules are literal; no user-configurable glob matcher is needed.
export async function analyzeCommits(commits) {
  if (!Array.isArray(commits) || commits.length > 500)
    throw new PlanError("commit-budget");
  let bytes = 0;
  for (const commit of commits) {
    if (
      !commit ||
      typeof commit.hash !== "string" ||
      !shaPattern.test(commit.hash) ||
      typeof commit.message !== "string"
    )
      throw new PlanError("invalid-commit");
    bytes += Buffer.byteLength(commit.message);
    if (Buffer.byteLength(commit.message) > 16_384 || bytes > maximumBytes)
      throw new PlanError("commit-byte-budget");
    if (commit.message.split("\n").some((line) => line.length > 1_024))
      throw new PlanError("commit-line-budget");
  }
  // Validate the whole batch before invoking upstream regex-based parsing.
  // Long unbroken lines must never reach that parser, even in rejected batches.
  const parser = new CommitParser((await angular()).parser);
  const parsed = [];
  for (const commit of commits) {
    if (!commit.message.trim()) continue;
    parsed.push({
      ...parser.parse(commit.message),
      hash: commit.hash,
      message: commit.message,
    });
  }
  let releaseType = null;
  for (const commit of filterRevertedCommitsSync(parsed)) {
    const current = commit.notes?.length
      ? "major"
      : commit.revert
        ? "patch"
        : Object.hasOwn(typeRules, commit.type)
          ? typeRules[commit.type]
          : null;
    if ((ranks[current] ?? 0) > (ranks[releaseType] ?? 0))
      releaseType = current;
  }
  return releaseType;
}

function gitReader(repository) {
  const deadline = performance.now() + 30_000;
  return (...args) => {
    const remaining = Math.floor(deadline - performance.now());
    if (remaining <= 0) throw new PlanError("git-deadline");
    try {
      return execFileSync(
        "git",
        [
          "--no-replace-objects",
          "--no-pager",
          "-c",
          "color.ui=false",
          "-C",
          repository,
          ...args,
        ],
        {
          encoding: "utf8",
          timeout: Math.min(10_000, remaining),
          maxBuffer: maximumBytes,
          stdio: ["ignore", "pipe", "pipe"],
          env: {
            PATH: process.env.PATH,
            LANG: "C.UTF-8",
            LC_ALL: "C",
            GIT_CONFIG_GLOBAL: "/dev/null",
            GIT_CONFIG_SYSTEM: "/dev/null",
            GIT_CONFIG_NOSYSTEM: "1",
            GIT_OPTIONAL_LOCKS: "0",
            GIT_TERMINAL_PROMPT: "0",
          },
        },
      );
    } catch {
      throw new PlanError("git-read-failed");
    }
  };
}

function validatePolicy(read, sha) {
  const names = read("ls-tree", "--name-only", sha).trim().split("\n");
  if (
    names.some(
      (name) =>
        (name.startsWith(".releaserc") && name !== ".releaserc.json") ||
        name.startsWith("release.config."),
    )
  ) {
    throw new PlanError("unsupported-config");
  }
  let policy;
  try {
    const text = read("show", `${sha}:.releaserc.json`);
    if (Buffer.byteLength(text) > 8_192) throw new PlanError("policy-budget");
    policy = JSON.parse(text);
    if (names.includes("package.json")) {
      const text = read("show", `${sha}:package.json`);
      if (Buffer.byteLength(text) > 131_072)
        throw new PlanError("policy-budget");
      if (Object.hasOwn(JSON.parse(text), "release"))
        throw new PlanError("unsupported-config");
    }
  } catch (error) {
    if (error instanceof PlanError) throw error;
    throw new PlanError("invalid-policy");
  }
  if (
    !policy ||
    Object.keys(policy).length !== 3 ||
    JSON.stringify(policy.branches) !==
      JSON.stringify(expectedPolicy.branches) ||
    policy.tagFormat !== expectedPolicy.tagFormat ||
    JSON.stringify(policy.plugins) !== JSON.stringify(expectedPolicy.plugins)
  )
    throw new PlanError("unsupported-config");
}

export async function planRelease(
  repository,
  candidateSha,
  { requireCheckout = true } = {},
) {
  if (
    typeof repository !== "string" ||
    typeof candidateSha !== "string" ||
    !shaPattern.test(candidateSha)
  )
    throw new PlanError("invalid-configuration");
  const read = gitReader(repository);
  if (read("rev-parse", "--is-shallow-repository").trim() !== "false")
    throw new PlanError("shallow-history");
  if (
    read("rev-parse", "--verify", `${candidateSha}^{commit}`).trim() !==
    candidateSha
  )
    throw new PlanError("invalid-candidate");
  if (requireCheckout && read("rev-parse", "HEAD").trim() !== candidateSha)
    throw new PlanError("candidate-mismatch");
  validatePolicy(read, candidateSha);
  const tags = read(
    "for-each-ref",
    "--count=501",
    `--merged=${candidateSha}`,
    "--format=%(refname:strip=2)",
    "refs/tags/v*",
  )
    .trim()
    .split("\n")
    .filter(Boolean);
  if (tags.length > 500) throw new PlanError("tag-budget");
  if (
    tags.some(
      (tag) =>
        semver.valid(tag.slice(1)) &&
        (semver.prerelease(tag.slice(1)) || tag.includes("+")),
    )
  )
    throw new PlanError("unsupported-version-tag");
  const versions = tags.filter(
    (tag) =>
      /^v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/.test(tag) &&
      semver.valid(tag.slice(1)),
  );
  versions.sort((a, b) => semver.rcompare(a.slice(1), b.slice(1)));
  if (!versions.length) throw new PlanError("missing-release-base");
  const baseTag = versions[0];
  const baseSha = read("rev-parse", "--verify", `${baseTag}^{commit}`).trim();
  const common = {
    schemaVersion: 1,
    policyVersion: "wetmap-angular-default-v1",
    readOnly: true,
    publishingEnabled: false,
    candidateSha,
    baseTag,
    baseSha,
  };
  if (baseSha === candidateSha)
    return {
      ...common,
      decision: "already-tagged",
      releaseType: null,
      proposedTag: null,
      commitCount: 0,
    };
  const hashes = read(
    "rev-list",
    "--max-count=501",
    `${baseTag}..${candidateSha}`,
  )
    .trim()
    .split("\n")
    .filter(Boolean);
  if (!hashes.length || hashes.length > 500)
    throw new PlanError("commit-budget");
  const data = read(
    "log",
    "--no-show-signature",
    "--no-notes",
    "--format=%H%x00%B%x00",
    `${baseTag}..${candidateSha}`,
  ).split("\0");
  if (data.pop().trim() !== "" || data.length !== hashes.length * 2)
    throw new PlanError("invalid-git-contract");
  const commits = [];
  for (let index = 0; index < data.length; index += 2)
    commits.push({ hash: data[index].trim(), message: data[index + 1] });
  if (
    new Set(commits.map((commit) => commit.hash)).size !== hashes.length ||
    commits.some((commit) => !hashes.includes(commit.hash))
  )
    throw new PlanError("invalid-git-contract");
  const releaseType = await analyzeCommits(commits);
  const next = releaseType ? semver.inc(baseTag.slice(1), releaseType) : null;
  if (releaseType && !next) throw new PlanError("invalid-version");
  return {
    ...common,
    decision: next ? "proposed" : "no-release",
    releaseType,
    proposedTag: next ? `v${next}` : null,
    commitCount: commits.length,
  };
}

export async function main(args = process.argv.slice(2)) {
  try {
    const { values } = parseArgs({
      args,
      options: {
        repo: { type: "string", default: process.cwd() },
        sha: { type: "string" },
      },
      allowPositionals: false,
    });
    const plan = await planRelease(values.repo, values.sha);
    console.log(JSON.stringify(plan));
    return 0;
  } catch (error) {
    console.error(
      JSON.stringify({
        event: "release.plan.failed",
        code: error instanceof PlanError ? error.code : "planner-failed",
      }),
    );
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  process.exitCode = await main();
