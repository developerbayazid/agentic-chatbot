"use client";

import { AlertCircle, FileText, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { errorMessage } from "@/lib/api/errors";
import {
  useDeleteDocument,
  useDocuments,
} from "@/features/documents/hooks/use-documents";
import {
  formatBytes,
  UploadDropzone,
} from "@/features/documents/components/upload-dropzone";

/** Documents: the same quiet language as conversations — a list, not a dashboard. */
export default function DocumentsPage() {
  const documents = useDocuments();
  const remove = useDeleteDocument();
  const maxBytes = 20_000_000;

  async function del(docId: string, title: string) {
    try {
      await remove.mutateAsync(docId);
      toast.success(`Deleted ${title}.`);
    } catch (cause) {
      toast.error(errorMessage(cause));
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8">
      <header>
        <h1 className="text-[19px] font-medium tracking-tight">Documents</h1>
        <p className="mt-1.5 max-w-xl text-[13.5px] leading-relaxed text-muted">
          Uploaded files are chunked, embedded, and indexed into your own
          namespace. The assistant can then answer from them.
        </p>
      </header>

      <div className="mt-6">
        <UploadDropzone maxBytes={maxBytes} onUploaded={() => void documents.refetch()} />
      </div>

      {documents.isLoading && (
        <div className="mt-5 space-y-1.5">
          <Skeleton className="h-11" />
          <Skeleton className="h-11" />
        </div>
      )}

      {documents.isError && (
        <div className="mt-5 flex items-start gap-2 rounded-xl border border-danger/25 bg-danger-soft p-3 text-[13px]">
          <AlertCircle className="mt-0.5 size-4 text-danger" />
          <div>
            <p className="text-danger">Could not load documents.</p>
            <p className="mt-1 text-muted">{errorMessage(documents.error)}</p>
          </div>
        </div>
      )}

      {!documents.isLoading &&
        !documents.isError &&
        documents.data?.documents.length === 0 && (
          <p className="mt-5 rounded-xl border border-dashed border-border-strong px-4 py-8 text-center text-[13.5px] text-muted">
            No documents yet. Upload one to start building your knowledge base.
          </p>
        )}

      {documents.data && documents.data.documents.length > 0 && (
        <section aria-label="Indexed documents" className="mt-6">
          <h2 className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">
            {documents.data.documents.length} indexed
            {documents.data.namespaces.length > 0 &&
              ` · ${documents.data.namespaces.join(", ")}`}
          </h2>

          <ul className="divide-y divide-border">
            {documents.data.documents.map((document) => (
              <li
                key={document.doc_id}
                className="group flex items-center gap-3 px-1 py-2.5"
              >
                <FileText className="size-4 shrink-0 text-muted" />

                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13.5px] text-foreground">
                    {document.title}
                  </p>
                  <p className="text-[11.5px] text-muted">
                    {formatBytes(document.size_bytes)}
                    <span className="mx-1.5" aria-hidden>·</span>
                    <span className="font-mono">{document.namespace}</span>
                    {document.updated_at && (
                      <>
                        <span className="mx-1.5" aria-hidden>·</span>
                        {document.updated_at}
                      </>
                    )}
                  </p>
                </div>

                <div className="opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                  <ConfirmDialog
                    title={`Delete ${document.title}?`}
                    description="Its chunks and vectors are removed, so the assistant can no longer answer from it."
                    confirmLabel="Delete"
                    destructive
                    onConfirm={() => void del(document.doc_id, document.title)}
                    trigger={
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Delete ${document.title}`}
                        disabled={remove.isPending}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    }
                  />
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
