// web/src/components/DocumentDrawer.tsx
// A document two ways: the text an AI agent receives (hidden parts in red) and the
// page a person sees. The page is shown in a sandboxed frame with scripts off:
// the document's own code never runs here.
import { EyeOff, FileText, Radar, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import type { DocumentResponse } from "../contract";
import { api } from "../lib/api";
import { DOC_KIND, plural, TRUST } from "../lib/words";
import { Badge, Button, Drawer, Loading, Segmented } from "./ui";

export function DocumentDrawer({ documentId, onClose, onPreview }: {
  documentId: string | null;
  onClose: () => void;
  onPreview: ((id: string) => void) | null; // null when there is nothing to preview yet
}) {
  const [doc, setDoc] = useState<DocumentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"read" | "seen">("read");

  useEffect(() => {
    if (!documentId) return;
    let live = true;
    setDoc(null);
    setError(null);
    setTab("read");
    api.document(documentId)
      .then((d) => live && setDoc(d))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [documentId]);

  const hidden = doc?.segments.filter((s) => s.hidden).length ?? 0;

  return (
    <Drawer
      open={documentId !== null}
      onClose={onClose}
      title={doc?.title ?? "Document"}
      subtitle={doc ? DOC_KIND[doc.kind] : undefined}
      icon={
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600">
          <FileText className="size-[18px]" />
        </span>
      }
    >
      {error && <p className="m-5 rounded-xl bg-rose-50 p-4 text-[13px] text-rose-800">{error}</p>}
      {!doc && !error && <Loading />}
      {doc && (
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={TRUST[doc.trust].tone} title={TRUST[doc.trust].hint}>{TRUST[doc.trust].label}</Badge>
            {hidden > 0 && <Badge tone="red" icon={<EyeOff />}>{plural(hidden, "hidden part")}</Badge>}
          </div>

          {onPreview && doc.trust !== "quarantined" && (
            <div className="flex flex-wrap items-center gap-3 rounded-xl bg-slate-50 px-3.5 py-3 ring-1 ring-inset ring-slate-200/70">
              <p className="min-w-[200px] flex-1 text-[12.5px] leading-5 text-slate-600">
                Not sure about this document? See exactly what depends on it before deciding. The preview runs on
                a copy of the memory.
              </p>
              <Button variant="dangerOutline" size="sm" icon={<Radar />} onClick={() => onPreview(doc.id)}>
                What if we stop trusting it?
              </Button>
            </div>
          )}

          {doc.html && (
            <Segmented
              value={tab}
              onChange={setTab}
              options={[
                { value: "read", label: "What the AI reads" },
                { value: "seen", label: "What a person sees" },
              ]}
            />
          )}

          {tab === "read" ? (
            <div className="space-y-3">
              {hidden > 0 && (
                <div className="flex gap-2.5 rounded-xl bg-rose-50 px-3.5 py-3 text-[12.5px] leading-5 text-rose-900 ring-1 ring-rose-200">
                  <ShieldAlert className="mt-0.5 size-4 shrink-0 text-rose-600" />
                  <p>
                    The parts in red never appear on the page a person sees, but an AI agent reading the page receives
                    them as ordinary text. This is how instructions get smuggled into an agent's memory.
                  </p>
                </div>
              )}
              {doc.segments.map((s, i) =>
                s.hidden ? (
                  <div key={i} className="rounded-xl border border-rose-200 bg-rose-50/70 p-3.5">
                    <div className="mb-1.5 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.07em] text-rose-700">
                      <EyeOff className="size-3.5" />
                      {s.kind === "comment" ? "Hidden comment: invisible on the page" : "Invisible text: styled so people can't see it"}
                    </div>
                    <p className="whitespace-pre-wrap font-mono text-[12px] leading-5 text-rose-950">{s.text}</p>
                  </div>
                ) : (
                  <p key={i} className="whitespace-pre-wrap text-[13.5px] leading-6 text-slate-700">{s.text}</p>
                ),
              )}
            </div>
          ) : (
            <div className="space-y-2">
              <iframe
                title={`${doc.title}, as a person sees it`}
                sandbox=""
                referrerPolicy="no-referrer"
                srcDoc={doc.html ?? ""}
                className="h-[520px] w-full rounded-xl border border-slate-200 bg-white"
              />
              <p className="text-[11.5px] text-slate-500">
                Shown in a sandbox with scripts turned off: the page's own code never runs here.
              </p>
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}
