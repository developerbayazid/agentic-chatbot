/**
 * Minimal Server-Sent Events parser for the BAYAZID AI stream contract.
 *
 * The backend emits frames of the form:
 *
 *   event: token
 *   data: {"content":"Hello"}
 *
 *   (blank line terminates a frame)
 *
 * This is deliberately our own parser rather than `EventSource`, because
 * `EventSource` cannot POST a JSON body and cannot be aborted once open.
 */

export interface SseEvent {
  event: string;
  data: string;
  id?: string;
}

/**
 * Incremental frame parser. Feed it decoded text in any chunking; it buffers
 * until a complete frame (terminated by a blank line) is available.
 */
export class SseParser {
  private buffer = "";

  /** Append a chunk and return any frames it completed. */
  push(chunk: string): SseEvent[] {
    this.buffer += chunk;

    // Frames are separated by a blank line; normalise CRLF first.
    this.buffer = this.buffer.replace(/\r\n/g, "\n");

    const frames: SseEvent[] = [];
    let boundary = this.buffer.indexOf("\n\n");

    while (boundary !== -1) {
      const raw = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);

      const parsed = parseFrame(raw);

      if (parsed) {
        frames.push(parsed);
      }

      boundary = this.buffer.indexOf("\n\n");
    }

    return frames;
  }

  /** Flush a final frame that arrived without a trailing blank line. */
  flush(): SseEvent[] {
    const remainder = this.buffer.trim();

    this.buffer = "";

    if (!remainder) {
      return [];
    }

    const parsed = parseFrame(remainder);

    return parsed ? [parsed] : [];
  }
}

function parseFrame(raw: string): SseEvent | null {
  let event = "message";
  let id: string | undefined;
  const dataLines: string[] = [];

  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) {
      continue;
    }

    const separator = line.indexOf(":");

    if (separator === -1) {
      continue;
    }

    const field = line.slice(0, separator);
    // A single leading space after the colon is part of the format, not data.
    const value = line.slice(separator + 1).replace(/^ /, "");

    if (field === "event") {
      event = value;
    } else if (field === "data") {
      dataLines.push(value);
    } else if (field === "id") {
      id = value;
    }
  }

  if (event === "message" && dataLines.length === 0) {
    return null;
  }

  return { event, data: dataLines.join("\n"), id };
}

/** Parse `data` as JSON, returning null instead of throwing on a bad frame. */
export function parseData<T>(event: SseEvent): T | null {
  try {
    return JSON.parse(event.data) as T;
  } catch {
    return null;
  }
}
