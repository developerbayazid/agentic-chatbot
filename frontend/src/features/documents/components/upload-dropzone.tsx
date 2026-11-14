"use client";

import { FileUp, Loader2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils/cn";
import { useUploadDocument } from "@/features/documents/hooks/use-documents";

/** The suffixes the backend accepts (loaders.SUPPORTED_SUFFIXES). */
export const ACCEPTED_EXTENSIONS = [".md", ".markdown", ".txt", ".rst", ".pdf"];

export function UploadDropzone({
  maxBytes,
  onUploaded,
}: {
  maxBytes: number;
  onUploaded: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadDocument();
  const [dragging, setDragging] = useState(false);

  async function handleFile(file: File | undefined) {
    if (!file) return;

    // Pre-flight mirrors the backend's rules so an obvious mistake costs no
    // round trip. The backend validates again and remains authoritative.
    const lower = file.name.toLowerCase();

    if (!ACCEPTED_EXTENSIONS.some((extension) => lower.endsWith(extension))) {
      toast.error(`Unsupported file type. Use ${ACCEPTED_EXTENSIONS.join(", ")}.`);
      return;
    }

    if (file.size === 0) {
      toast.error("That file is empty.");
      return;
    }

    if (file.size > maxBytes) {
      toast.error(
        `That file is ${formatBytes(file.size)}; the limit is ${formatBytes(maxBytes)}.`,
      );
      return;
    }

    try {
      const result = await upload.mutateAsync(file);

      toast.success(
        result.skipped
          ? `${result.document.title} was already indexed — nothing changed.`
          : `Indexed ${result.document.title} (${result.chunks_created} chunks).`,
      );

      if (result.warning) toast.warning(result.warning);

      onUploaded();
    } catch (cause) {
      toast.error(errorMessage(cause));
    }
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        void handleFile(event.dataTransfer.files[0]);
      }}
      className={cn(
        "rounded-xl border border-dashed border-border-strong px-4 py-7 text-center transition-colors",
        dragging && "border-accent bg-surface",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS.join(",")}
        className="sr-only"
        onChange={(event) => {
          void handleFile(event.target.files?.[0]);
          event.target.value = "";
        }}
      />

      <FileUp className="mx-auto size-5 text-muted" />
      <p className="mt-2 text-[13.5px] text-foreground">Drop a document here</p>
      <p className="mt-1 text-[11.5px] text-muted">
        {ACCEPTED_EXTENSIONS.join(" · ")} · up to {formatBytes(maxBytes)}
      </p>

      <Button
        variant="secondary"
        size="sm"
        className="mt-3.5"
        disabled={upload.isPending}
        onClick={() => inputRef.current?.click()}
      >
        {upload.isPending ? <Loader2 className="animate-spin" /> : <Upload />}
        {upload.isPending ? "Uploading…" : "Choose a file"}
      </Button>
    </div>
  );
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
