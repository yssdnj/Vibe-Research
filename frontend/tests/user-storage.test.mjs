import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");

test("private watchlist and notes use authenticated API storage", async () => {
  const [watchlist, notes, api] = await Promise.all([
    read("lib/watchlist.ts"), read("lib/notes.ts"), read("lib/api.ts"),
  ]);
  assert.doesNotMatch(watchlist, /vr-watchlist|localStorage/);
  assert.doesNotMatch(notes, /vr-notes|localStorage|storageSet|storageRemove/);
  assert.match(api, /watchlist:\s*\(\)/);
  assert.match(api, /saveWatchlist/);
  assert.match(api, /notes:\s*\(\)/);
  assert.match(api, /saveChat/);
});

test("Ask AI history uses the user-scoped chat API", async () => {
  const source = await read("components/ui/AskAiButton.tsx");
  assert.doesNotMatch(source, /CHAT_KEY_PREFIX|storageGet|storageSet|storageRemove/);
  assert.match(source, /api\.chat/);
  assert.match(source, /api\.saveChat/);
  assert.match(source, /api\.clearChat/);
});
