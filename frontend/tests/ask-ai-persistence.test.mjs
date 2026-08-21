import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const SRC = new URL("../src/components/ui/AskAiButton.tsx", import.meta.url);
const source = await readFile(SRC, "utf8");

test("Ask AI persists through authenticated user chat APIs", () => {
  assert.match(source, /api\.chat\(chatKey\)/);
  assert.match(source, /api\.saveChat\(chatKey, keep\)/);
  assert.match(source, /api\.clearChat\(chatKey\)/);
  assert.doesNotMatch(source, /localStorage|storageGet|storageSet|storageRemove/);
});

test("conversations are scoped by route and optional entity key", () => {
  assert.match(source, /useLocation/);
  assert.match(source, /pathname\.replace\(\/\^\\\/\+\/, ""\) \|\| "home"/);
  assert.match(source, /scopeKey\?: string/);
});

test("persisted history is bounded and incomplete turns are removed", () => {
  assert.match(source, /MAX_PERSISTED_MSGS\s*=\s*40/);
  assert.match(source, /completeTurns\(chat\.msgs\)\.slice\(-MAX_PERSISTED_MSGS\)/);
  assert.match(source, /if \(out\.length && out\[out\.length - 1\]\.role === "user"\) out\.pop\(\);/);
});

test("route changes abort streams and ignore stale chat loads", () => {
  assert.match(source, /abortRef\.current\?\.abort\(\)/);
  assert.match(source, /active && chatKeyRef\.current === chatKey/);
  assert.match(source, /return \(\) => \{ active = false; \}/);
});

test("streaming replies persist only after successful completion", () => {
  assert.match(source, /role: "assistant", content: "", tools: \[\], partial: true/);
  assert.match(source, /const \{ partial: _drop, \.\.\.rest \} = msg;/);
  assert.match(source, /completeTurns\(msgs\)\.map/);
});

test("aborted-request cleanup remains gated by request identity", () => {
  const block = source.match(/\} catch \(e\) \{[\s\S]*?\} finally \{/);
  assert.ok(block);
  assert.match(block[0], /const superseded = abortRef\.current !== null && abortRef\.current !== ac;/);
  assert.match(block[0], /if \(!superseded && chatKeyRef\.current === startedKey\)/);
  assert.match(block[0], /const dropUser = m\[m\.length - 2\]\?\.role === "user";/);
});

test("the stock page passes a per-symbol scope", async () => {
  const page = await readFile(new URL("../src/pages/StockData.tsx", import.meta.url), "utf8");
  assert.match(page, /<AskAiButton[\s\S]*?scopeKey=/);
});
