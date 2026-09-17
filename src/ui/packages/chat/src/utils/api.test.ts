// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it, vi } from "vitest";

import { handleChatStreamResponse } from "@/utils/api";

/**
 * Builds a Response whose body yields the given text split into fixed-size
 * chunks, the way a network read does. The sources frame carries every reranked
 * document, so it is large enough to straddle a read boundary; splitting at an
 * arbitrary size reproduces that.
 */
const streamOf = (text: string, chunkSize: number): Response => {
  const bytes = new TextEncoder().encode(text);
  let offset = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (offset >= bytes.length) {
        controller.close();
        return;
      }
      controller.enqueue(bytes.slice(offset, offset + chunkSize));
      offset += chunkSize;
    },
  });
  return new Response(body);
};

const answerFrame = (content: string) =>
  `data: ${JSON.stringify({ choices: [{ index: 0, delta: { content } }] })}`;

const sourcesFrame = (docs: unknown[]) =>
  `json: ${JSON.stringify({ reranked_docs: docs })}`;

const docsWithText = (count: number, textLength: number) =>
  Array.from({ length: count }, (_, i) => ({
    text: `${i}`.padEnd(textLength, "x"),
    citation_id: i + 1,
    type: "file",
    object_name: `doc-${i}.pdf`,
  }));

describe("handleChatStreamResponse", () => {
  it("reports sources when the frame arrives whole", async () => {
    const onAnswer = vi.fn();
    const onSources = vi.fn();
    const docs = docsWithText(2, 10);
    const stream = [
      answerFrame("hello"),
      sourcesFrame(docs),
      "data: [DONE]",
    ].join("\n\n");

    await handleChatStreamResponse(
      streamOf(stream, 65536),
      onAnswer,
      onSources,
    );

    expect(onSources).toHaveBeenLastCalledWith(docs);
    expect(onAnswer).toHaveBeenCalledWith("hello");
  });

  it.each([256, 1024, 4096])(
    "reassembles a sources frame split across reads (chunk size %i)",
    async (chunkSize) => {
      const onAnswer = vi.fn();
      const onSources = vi.fn();
      // 20 documents of ~600 chars is the shape a real answer produces, and it
      // cannot fit in one read at these sizes.
      const docs = docsWithText(20, 600);
      const stream = [
        answerFrame("hello"),
        sourcesFrame(docs),
        "data: [DONE]",
      ].join("\n\n");

      await handleChatStreamResponse(
        streamOf(stream, chunkSize),
        onAnswer,
        onSources,
      );

      // Parsing a truncated frame used to fail and report zero sources, which is
      // indistinguishable in the UI from an answer that genuinely has none.
      expect(onSources).toHaveBeenLastCalledWith(docs);
      expect(onSources).not.toHaveBeenCalledWith([]);
    },
  );

  it("keeps earlier sources when a later frame is unparseable", async () => {
    const onAnswer = vi.fn();
    const onSources = vi.fn();
    const docs = docsWithText(2, 10);
    const stream = [
      sourcesFrame(docs),
      'json: {"reranked_docs": [ truncated',
      "data: [DONE]",
    ].join("\n\n");

    await handleChatStreamResponse(
      streamOf(stream, 65536),
      onAnswer,
      onSources,
    );

    expect(onSources).toHaveBeenLastCalledWith(docs);
    expect(onSources).not.toHaveBeenCalledWith([]);
  });

  it("handles a trailing frame that has no separator after it", async () => {
    const onAnswer = vi.fn();
    const onSources = vi.fn();
    const docs = docsWithText(3, 400);
    const stream = [answerFrame("hi"), sourcesFrame(docs)].join("\n\n");

    await handleChatStreamResponse(streamOf(stream, 512), onAnswer, onSources);

    expect(onSources).toHaveBeenLastCalledWith(docs);
  });

  it("ends the stream only on a terminator frame, not on text containing one", async () => {
    const onAnswer = vi.fn();
    const onSources = vi.fn();
    const docs = docsWithText(2, 10);
    // An answer may legitimately mention the marker; a substring test would drop
    // this frame and lose the text, and would skip the sources frame after it.
    const stream = [
      answerFrame("the log ends with [DONE] today"),
      sourcesFrame(docs),
      "data: [DONE]",
    ].join("\n\n");

    await handleChatStreamResponse(
      streamOf(stream, 65536),
      onAnswer,
      onSources,
    );

    expect(onAnswer).toHaveBeenCalledWith("the log ends with [DONE] today");
    expect(onSources).toHaveBeenLastCalledWith(docs);
  });

  it("does not split a multi-byte character across reads", async () => {
    const onAnswer = vi.fn();
    const onSources = vi.fn();
    const docs = [
      { text: "zażółć gęślą jaźń — ∞", citation_id: 1, type: "file" },
    ];
    const stream = [sourcesFrame(docs), "data: [DONE]"].join("\n\n");

    // A small read size lands mid-sequence for the multi-byte characters above.
    await handleChatStreamResponse(streamOf(stream, 7), onAnswer, onSources);

    expect(onSources).toHaveBeenLastCalledWith(docs);
  });
});
