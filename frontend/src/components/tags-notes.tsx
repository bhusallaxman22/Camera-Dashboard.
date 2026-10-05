"use client";

import { Plus, X } from "lucide-react";
import { useState } from "react";
import type { PhotoUpdate, Tag } from "@/lib/types";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

export function TagsNotes({
  tags,
  notes,
  onUpdate,
}: {
  tags: Tag[];
  notes: string | null;
  onUpdate: (body: PhotoUpdate) => void;
}) {
  const [draft, setDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState(notes ?? "");
  const names = tags.map((t) => t.name);

  const addTag = () => {
    const name = draft.trim().toLowerCase();
    if (!name || names.includes(name)) return setDraft("");
    onUpdate({ tags: [...names, name] });
    setDraft("");
  };

  return (
    <div className="space-y-3" data-testid="tags-notes">
      <div className="flex flex-wrap items-center gap-1.5">
        {tags.map((t) => (
          <span
            key={t.id}
            className="bg-ink-800 text-ink-200 flex items-center gap-1 rounded-full py-0.5 pr-1 pl-2.5 text-xs"
          >
            {t.name}
            <button
              type="button"
              onClick={() => onUpdate({ tags: names.filter((n) => n !== t.name) })}
              className="text-ink-500 hover:bg-ink-700 hover:text-ink-100 rounded-full p-0.5"
              aria-label={`Remove tag ${t.name}`}
            >
              <X className="size-3" />
            </button>
          </span>
        ))}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            addTag();
          }}
          className="flex items-center gap-1"
        >
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add tag"
            className="h-7 w-28 text-xs"
            aria-label="New tag"
            maxLength={64}
          />
          <Button type="submit" size="icon" variant="ghost" aria-label="Add tag" className="size-7">
            <Plus className="size-3.5" />
          </Button>
        </form>
      </div>
      <textarea
        value={noteDraft}
        onChange={(e) => setNoteDraft(e.target.value)}
        onBlur={() => {
          if ((notes ?? "") !== noteDraft) onUpdate({ notes: noteDraft });
        }}
        rows={3}
        maxLength={10000}
        placeholder="Notes (saved when you click away)"
        className="border-ink-700 bg-ink-850 text-ink-100 placeholder:text-ink-500 focus:border-accent/60 w-full resize-y rounded-md border px-2.5 py-2 text-sm focus:outline-none"
        aria-label="Notes"
      />
    </div>
  );
}
