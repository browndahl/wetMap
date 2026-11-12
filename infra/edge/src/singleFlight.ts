// Isolate-local coalescing only, not a cross-region lock.
interface Snapshot {
  body: string;
  status: number;
  headers: [string, string][];
}
const operations = new WeakMap<object, Map<string, Promise<Snapshot>>>();
export function coalesceResponse(
  scope: object,
  key: string,
  load: () => Promise<Response>,
): Promise<Response> {
  let pending = operations.get(scope);
  if (!pending) {
    pending = new Map();
    operations.set(scope, pending);
  }
  let response = pending.get(key);
  if (!response) {
    response = load()
      .then(async (value) => ({
        body: await value.text(),
        status: value.status,
        headers: [...value.headers.entries()] as [string, string][],
      }))
      .finally(() => pending!.delete(key));
    pending.set(key, response);
  }
  // Share only immutable, bounded JSON, never a request-owned I/O stream across
  // Workers invocations. Every caller receives its own readable body.
  return response.then(
    (value) =>
      new Response(value.body, {
        status: value.status,
        headers: value.headers,
      }),
  );
}
