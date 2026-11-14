import { describe, expect, it } from "vitest";

import { parseData, SseParser } from "@/lib/api/sse";

describe("SseParser", () => {
  it("parses one complete frame", () => {
    const parser = new SseParser();

    expect(parser.push('event: token\ndata: {"content":"Hi"}\n\n')).toEqual([
      { event: "token", data: '{"content":"Hi"}', id: undefined },
    ]);
  });

  it("buffers a frame that arrives in pieces", () => {
    const parser = new SseParser();

    expect(parser.push('event: tok')).toEqual([]);
    expect(parser.push('en\ndata: {"content":')).toEqual([]);
    expect(parser.push('"Hi"}\n\n')).toEqual([
      { event: "token", data: '{"content":"Hi"}', id: undefined },
    ]);
  });

  it("returns several frames from one chunk", () => {
    const parser = new SseParser();
    const frames = parser.push(
      'event: thread\ndata: {"thread_id":"t1"}\n\n' +
        'event: status\ndata: {"status":"processing"}\n\n',
    );

    expect(frames.map((frame) => frame.event)).toEqual(["thread", "status"]);
  });

  it("handles CRLF line endings", () => {
    const parser = new SseParser();

    expect(parser.push('event: token\r\ndata: {"content":"x"}\r\n\r\n')).toHaveLength(
      1,
    );
  });

  it("joins multiple data lines", () => {
    const parser = new SseParser();
    const [frame] = parser.push("event: token\ndata: a\ndata: b\n\n");

    expect(frame.data).toBe("a\nb");
  });

  it("ignores comments and unknown fields", () => {
    const parser = new SseParser();
    const [frame] = parser.push(
      ': keep-alive\nevent: token\nretry: 100\ndata: {"content":"x"}\n\n',
    );

    expect(frame).toEqual({ event: "token", data: '{"content":"x"}', id: undefined });
  });

  it("flushes a trailing frame without a blank line", () => {
    const parser = new SseParser();

    parser.push('event: final\ndata: {"title":null}');

    expect(parser.flush()).toEqual([
      { event: "final", data: '{"title":null}', id: undefined },
    ]);
  });

  it("returns nothing when flushing an empty buffer", () => {
    expect(new SseParser().flush()).toEqual([]);
  });

  it("does not throw on malformed data", () => {
    const parser = new SseParser();
    const [frame] = parser.push("event: token\ndata: {not json}\n\n");

    expect(parseData(frame)).toBeNull();
  });
});

describe("parseData", () => {
  it("decodes the backend's frames", () => {
    expect(
      parseData({ event: "approval_required", data: '{"approval_id":"a1"}' }),
    ).toEqual({ approval_id: "a1" });
  });
});
