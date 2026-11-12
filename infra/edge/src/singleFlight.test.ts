import { expect, it } from "vitest";
import { coalesceResponse } from "./singleFlight";
it("shares one cold operation but returns independent bodies", async () => {
  const scope = {};
  let calls = 0;
  const load = async () => {
    calls++;
    return new Response("forecast");
  };
  const responses = await Promise.all(
    Array.from({ length: 20 }, () => coalesceResponse(scope, "point", load)),
  );
  expect(calls).toBe(1);
  expect(
    await Promise.all(responses.map((response) => response.text())),
  ).toEqual(Array(20).fill("forecast"));
  await coalesceResponse(scope, "point", load);
  expect(calls).toBe(2);
});
it("releases failures and isolates buckets and coordinates", async () => {
  const scope = {};
  await expect(
    coalesceResponse(scope, "a", async () => {
      throw new Error("upstream");
    }),
  ).rejects.toThrow("upstream");
  const responses = await Promise.all([
    coalesceResponse(scope, "a", async () => new Response("a")),
    coalesceResponse(scope, "b", async () => new Response("b")),
    coalesceResponse({}, "a", async () => new Response("other")),
  ]);
  expect(
    await Promise.all(responses.map((response) => response.text())),
  ).toEqual(["a", "b", "other"]);
});
