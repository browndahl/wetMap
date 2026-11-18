import assert from "node:assert/strict";
import { test } from "node:test";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, writeFileSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { analyzeCommits, planRelease, PlanError } from "./plan.mjs";

const cli = fileURLToPath(new URL("./plan.mjs", import.meta.url));
const project = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const policy = {
  branches: ["main"],
  tagFormat: "v${version}",
  plugins: [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    "@semantic-release/github",
  ],
};
const safeEnv = {
  PATH: process.env.PATH,
  LANG: "C.UTF-8",
  GIT_CONFIG_GLOBAL: "/dev/null",
  GIT_CONFIG_NOSYSTEM: "1",
  GIT_AUTHOR_DATE: "2026-01-01T00:00:00Z",
  GIT_COMMITTER_DATE: "2026-01-01T00:00:00Z",
};
const hash = (index) =>
  createHash("sha1").update(`synthetic-fixture-${index}`).digest("hex");

function fixture(t) {
  const path = mkdtempSync(join(tmpdir(), "wetmap-release-plan-test-"));
  t.after(() => rmSync(path, { recursive: true, force: true }));
  const git = (...args) =>
    execFileSync(
      "git",
      [
        "-c",
        "user.name=Release Test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "-C",
        path,
        ...args,
      ],
      { encoding: "utf8", env: safeEnv, stdio: ["ignore", "pipe", "pipe"] },
    ).trim();
  git("init", "--template=", "-b", "main");
  git("config", "core.hooksPath", "/dev/null");
  writeFileSync(join(path, ".releaserc.json"), JSON.stringify(policy));
  let count = 0;
  const commit = (message) => {
    writeFileSync(join(path, "counter"), String(count++));
    git("add", ".");
    git("commit", "-m", message);
    return git("rev-parse", "HEAD");
  };
  const base = commit("chore: base");
  git("tag", "v1.2.3");
  return { path, git, commit, base };
}

// Golden inputs for the configured Angular/default policy, not custom/preset rules.
for (const [message, expected] of [
  ["fix: correction", "patch"],
  ["perf(api): reduce CPU", "patch"],
  ["feat: add rain view", "minor"],
  ["feat: API\n\nBREAKING CHANGE: removed field", "major"],
  ["fix: API\n\nBREAKING CHANGE: removed field", "major"],
  ["docs: text", null],
  ["chore(deps): update package", null],
  ["refactor: internal", null],
  ["test: checks", null],
  ["FIX: uppercase convention", "patch"],
  ["FEAT: uppercase convention", "minor"],
  ["Fix: mixed case", null],
  ["feat!: default Angular does not recognize bang syntax", null],
  ["feat(api)!: also not recognized", null],
  ["feat!: API\n\nBREAKING CHANGE: recognized footer", "major"],
  ["fix:no header space", null],
  ["Merge pull request #1\n\nfeat: body isn't header", null],
  ["revert: no recognized revert body", null],
  ["fix: docs mention BREAKING CHANGE inside subject", "patch"],
  ["docs: x\n\nBREAKING-CHANGE: not configured", null],
  ["\n\t ", null],
  ["feat(\u00f8): international scope", "minor"],
])
  test(`reference policy: ${JSON.stringify(message)}`, async () => {
    assert.equal(await analyzeCommits([{ hash: hash(1), message }]), expected);
  });

test("highest impact across a batch, independent of order", async () => {
  const rows = [
    "fix: one",
    "feat: two",
    "fix: three\n\nBREAKING CHANGE: API",
  ].map((message, index) => ({ hash: hash(index), message }));
  assert.equal(await analyzeCommits(rows), "major");
  assert.equal(await analyzeCommits(rows.reverse()), "major");
});

for (const short of [false, true])
  test(`reference revert filtering (${short ? "short hash is not equal" : "full hashes cancel"})`, async () => {
    const original = { hash: hash(7), message: "feat: feature" };
    const reverted = {
      hash: hash(8),
      message: `Revert "feat: feature"\n\nThis reverts commit ${short ? original.hash.slice(0, 7) : original.hash}.`,
    };
    // The unchanged upstream filter uses exact hash equality, not prefix matching.
    assert.equal(
      await analyzeCommits([reverted, original]),
      short ? "minor" : null,
    );
    assert.equal(
      await analyzeCommits([
        reverted,
        original,
        { hash: hash(9), message: "fix: retained" },
      ]),
      short ? "minor" : "patch",
    );
    assert.equal(await analyzeCommits([reverted]), "patch");
  });

test("reject oversized and malformed commit inputs without raw messages", async () => {
  for (const rows of [
    null,
    [{ hash: "bad", message: "private-sentinel" }],
    [{ hash: hash(1), message: "x".repeat(16_385) }],
    Array(501).fill({ hash: hash(1), message: "fix: x" }),
    Array(129).fill({
      hash: hash(1),
      message: `${"x".repeat(1_023)}\n`.repeat(16),
    }),
  ]) {
    await assert.rejects(
      analyzeCommits(rows),
      (error) =>
        error instanceof PlanError &&
        !error.message.includes("private-sentinel"),
    );
  }
});

test("long unbroken input is rejected before upstream regex parsing", async () => {
  await assert.rejects(
    analyzeCommits([{ hash: hash(1), message: "x".repeat(1_025) }]),
    { code: "commit-line-budget" },
  );
});

test("maximum accepted single line parses within a bounded child process", () => {
  const script = `import {analyzeCommits} from ${JSON.stringify(new URL("./plan.mjs", import.meta.url).href)};
    console.log(await analyzeCommits([{hash: ${JSON.stringify(hash(1))}, message: "x".repeat(1024)}]));`;
  const result = spawnSync(
    process.execPath,
    ["--input-type=module", "--eval", script],
    {
      env: safeEnv,
      encoding: "utf8",
      timeout: 2_000,
      maxBuffer: 16_384,
    },
  );
  assert.equal(result.status, 0, "parser must complete, not time out");
  assert.equal(result.stdout.trim(), "null");
});

for (const [message, version] of [
  ["fix: change", "v1.2.4"],
  ["feat: change", "v1.3.0"],
  ["fix: change\n\nBREAKING CHANGE: api", "v2.0.0"],
  ["docs: change", null],
]) {
  test(`local Git plan ${JSON.stringify(message)}`, async (t) => {
    const repo = fixture(t);
    const sha = repo.commit(message);
    const before = repo.git("show-ref");
    const plan = await planRelease(repo.path, sha);
    assert.equal(plan.proposedTag, version);
    assert.equal(plan.baseTag, "v1.2.3");
    assert.equal(plan.decision, version ? "proposed" : "no-release");
    assert.equal(plan.publishingEnabled, false);
    assert.equal(plan.readOnly, true);
    assert.equal(repo.git("show-ref"), before);
    assert.equal(repo.git("status", "--porcelain"), "");
  });
}

test("already tagged is not falsely called published or proposed", async (t) => {
  const repo = fixture(t);
  const plan = await planRelease(repo.path, repo.base);
  assert.equal(plan.decision, "already-tagged");
  assert.equal(plan.proposedTag, null);
  assert.equal(plan.publishingEnabled, false);
});

test("annotated stable tags are peeled; unrelated higher branch tags ignored", async (t) => {
  const repo = fixture(t);
  repo.git("switch", "-c", "unrelated");
  repo.commit("feat: other");
  repo.git("tag", "v99.0.0");
  repo.git("switch", "main");
  const first = repo.commit("fix: one");
  repo.git("tag", "-a", "v1.2.4", "-m", "release");
  const sha = repo.commit("fix: two");
  const plan = await planRelease(repo.path, sha);
  assert.equal(plan.baseSha, first);
  assert.equal(plan.baseTag, "v1.2.4");
  assert.equal(plan.proposedTag, "v1.2.5");
});

test("tag selection uses semver, not lexical order", async (t) => {
  const repo = fixture(t);
  repo.git("tag", "v1.9.0");
  repo.git("tag", "v1.10.0");
  repo.git("tag", "v-audit");
  const plan = await planRelease(repo.path, repo.commit("fix: next"));
  assert.equal(plan.baseTag, "v1.10.0");
  assert.equal(plan.proposedTag, "v1.10.1");
});

test("policy comes from candidate commit, not dirty worktree", async (t) => {
  const repo = fixture(t);
  const sha = repo.commit("fix: valid");
  writeFileSync(join(repo.path, ".releaserc.json"), "private-sentinel");
  const plan = await planRelease(repo.path, sha);
  assert.equal(plan.proposedTag, "v1.2.4");
  assert.equal(
    readFileSync(join(repo.path, ".releaserc.json"), "utf8"),
    "private-sentinel",
  );
});

test("local replace refs cannot hide a version-impacting commit", async (t) => {
  const repo = fixture(t);
  const candidate = repo.commit("feat: actual feature");
  repo.git("switch", "--detach", repo.base);
  const replacement = repo.commit("docs: replacement");
  repo.git("replace", candidate, replacement);
  repo.git("switch", "--detach", candidate);
  const before = repo.git("show-ref");
  const plan = await planRelease(repo.path, candidate);
  assert.equal(plan.proposedTag, "v1.3.0");
  assert.equal(repo.git("show-ref"), before);
});

for (const text of ["private-sentinel", "x".repeat(8_193)]) {
  test(`invalid or oversized policy fails without content leakage (${text.length} bytes)`, async (t) => {
    const repo = fixture(t);
    writeFileSync(join(repo.path, ".releaserc.json"), text);
    await assert.rejects(
      planRelease(repo.path, repo.commit("fix: x")),
      (error) =>
        error instanceof PlanError &&
        !error.message.includes("private-sentinel"),
    );
  });
}

for (const config of [
  { ...policy, releaseRules: [] },
  { ...policy, branches: ["other"] },
  { ...policy, plugins: [] },
  null,
]) {
  test(`unsupported policy fails closed: ${JSON.stringify(config)}`, async (t) => {
    const repo = fixture(t);
    writeFileSync(join(repo.path, ".releaserc.json"), JSON.stringify(config));
    await assert.rejects(planRelease(repo.path, repo.commit("fix: x")), {
      code: "unsupported-config",
    });
  });
}

for (const name of [".releaserc.yml", "release.config.js", "package.json"]) {
  test(`alternate config never executed: ${name}`, async (t) => {
    const repo = fixture(t);
    writeFileSync(
      join(repo.path, name),
      name === "package.json"
        ? '{"release":{}}'
        : "throw Error('private-sentinel')",
    );
    await assert.rejects(planRelease(repo.path, repo.commit("fix: x")), {
      code: "unsupported-config",
    });
  });
}

for (const tag of ["v2.0.0-beta.1", "v1.2.3+build"])
  test(`unsupported channel fails closed: ${tag}`, async (t) => {
    const repo = fixture(t);
    repo.git("tag", tag);
    await assert.rejects(planRelease(repo.path, repo.commit("fix: x")), {
      code: "unsupported-version-tag",
    });
  });

test("missing tag history is an error, not a fabricated first release", async (t) => {
  const repo = fixture(t);
  repo.git("tag", "-d", "v1.2.3");
  await assert.rejects(planRelease(repo.path, repo.base), {
    code: "missing-release-base",
  });
});

test("candidate checkout mismatch is rejected; historical replay is explicitly read-only", async (t) => {
  const repo = fixture(t);
  repo.commit("fix: new");
  await assert.rejects(planRelease(repo.path, repo.base), {
    code: "candidate-mismatch",
  });
  assert.equal(
    (await planRelease(repo.path, repo.base, { requireCheckout: false }))
      .decision,
    "already-tagged",
  );
});

test("shallow clone fails without writing or fetching", async (t) => {
  const source = fixture(t);
  source.commit("fix: next");
  const parent = mkdtempSync(join(tmpdir(), "wetmap-release-shallow-test-"));
  t.after(() => rmSync(parent, { recursive: true, force: true }));
  const destination = join(parent, "repo");
  execFileSync(
    "git",
    ["clone", "--depth=1", `file://${source.path}`, destination],
    { env: safeEnv, stdio: "pipe" },
  );
  await assert.rejects(
    planRelease(destination, source.git("rev-parse", "HEAD")),
    { code: "shallow-history" },
  );
});

test("read-only CLI rejects publisher flags and never prints secret-like input", async (t) => {
  const repo = fixture(t);
  for (const args of [
    ["--publish", "private-token-sentinel"],
    ["--sha", "private-token-sentinel"],
    [],
  ]) {
    const result = spawnSync(
      process.execPath,
      [cli, "--repo", repo.path, ...args],
      { encoding: "utf8", env: safeEnv },
    );
    assert.equal(result.status, 1);
    assert(
      !`${result.stdout}${result.stderr}`.includes("private-token-sentinel"),
    );
  }
  const before = repo.git("show-ref");
  const result = spawnSync(
    process.execPath,
    [cli, "--repo", repo.path, "--sha", repo.base],
    { encoding: "utf8", env: safeEnv },
  );
  assert.equal(result.status, 0);
  assert.equal(JSON.parse(result.stdout).publishingEnabled, false);
  assert.equal(repo.git("show-ref"), before);
});

test("real history replay reproduces all 13 v1.22.0–12 tags without changing source refs", async (t) => {
  const gitAt = (path, ...args) =>
    execFileSync("git", ["--no-replace-objects", "-C", path, ...args], {
      encoding: "utf8",
      env: safeEnv,
      stdio: "pipe",
      timeout: 10_000,
    }).trim();
  const sourceRefs = gitAt(project, "show-ref");
  const parent = mkdtempSync(join(tmpdir(), "wetmap-release-replay-test-"));
  t.after(() => rmSync(parent, { recursive: true, force: true }));
  const clone = join(parent, "history.git");
  execFileSync(
    "git",
    ["clone", "--bare", "--no-hardlinks", "--template=", project, clone],
    {
      env: safeEnv,
      stdio: "pipe",
      timeout: 20_000,
    },
  );
  for (let index = 0; index <= 12; index++) {
    const tag = `v1.22.${index}`;
    const object = gitAt(clone, "rev-parse", `refs/tags/${tag}`);
    const target = gitAt(clone, "rev-parse", `${tag}^{commit}`);
    // Remove only this tag in the disposable clone. Keep the candidate commit
    // and its actual predecessor tags, so the full intervening range is replayed.
    gitAt(clone, "update-ref", "-d", `refs/tags/${tag}`, object);
    try {
      const plan = await planRelease(clone, target, { requireCheckout: false });
      assert.equal(plan.proposedTag, tag, `actual historical release ${tag}`);
      assert.equal(plan.releaseType, index === 0 ? "minor" : "patch");
      assert.equal(plan.readOnly, true);
      assert.equal(plan.publishingEnabled, false);
      assert.equal(gitAt(project, "show-ref"), sourceRefs);
    } finally {
      gitAt(clone, "update-ref", `refs/tags/${tag}`, object);
    }
  }
  assert.equal(gitAt(project, "show-ref"), sourceRefs);
});
