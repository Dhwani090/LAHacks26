// LibraryUploader — drag-drop bulk uploader for a creator's past clips.
// PRD §11.6 + §7.6. Each upload runs TRIBE + Whisper + nomic-embed on the GX10
// and lands as a LibraryEntry in cache/library/<creator_id>/.
// On completion, calls onLibraryChange so the SimilarityPanel can refresh.
// See docs/PRD.md §11.6.
'use client';

import { useEffect, useRef, useState } from 'react';
import { brainClient } from '../lib/brainClient';
import { TUNING } from '../lib/tuning';
import type { LibraryEntryMeta } from '../lib/types';

type UploadStatus = 'pending' | 'uploading' | 'done' | 'error';

interface UploadItem {
  id: string;
  file: File;
  status: UploadStatus;
  message?: string;
}

interface Props {
  creatorId: string;
  onLibraryChange?: (size: number) => void;
}

export function LibraryUploader({ creatorId, onLibraryChange }: Props) {
  const [librarySize, setLibrarySize] = useState<number | null>(null);
  const [entries, setEntries] = useState<LibraryEntryMeta[]>([]);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [draggedOver, setDraggedOver] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!creatorId) return;
    const ac = new AbortController();
    brainClient
      .getLibrary(creatorId, ac.signal)
      .then((res) => {
        setLibrarySize(res.size);
        setEntries(res.entries);
        onLibraryChange?.(res.size);
      })
      .catch((err) => {
        if (ac.signal.aborted) return;
        console.error('[LibraryUploader] /library failed', err);
      });
    return () => ac.abort();
  }, [creatorId, onLibraryChange]);

  function enqueueFiles(files: FileList | File[]) {
    const arr = Array.from(files).filter((f) => f.type.startsWith('video/'));
    if (arr.length === 0) return;
    const items: UploadItem[] = arr.map((f) => ({
      id: `${f.name}-${f.size}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      file: f,
      status: 'pending',
    }));
    setUploads((prev) => [...prev, ...items]);
    void runUploads(items);
  }

  async function runUploads(items: UploadItem[]) {
    for (const item of items) {
      setUploads((prev) =>
        prev.map((u) => (u.id === item.id ? { ...u, status: 'uploading' } : u)),
      );
      try {
        const res = await brainClient.uploadLibraryEntry(creatorId, item.file);
        setUploads((prev) =>
          prev.map((u) => (u.id === item.id ? { ...u, status: 'done' } : u)),
        );
        setLibrarySize(res.library_size);
        onLibraryChange?.(res.library_size);
      } catch (err) {
        console.error('[LibraryUploader] upload failed', err);
        const msg = err instanceof Error ? err.message : 'upload failed';
        setUploads((prev) =>
          prev.map((u) =>
            u.id === item.id ? { ...u, status: 'error', message: msg } : u,
          ),
        );
      }
    }
    // Refresh listing after the batch.
    try {
      const res = await brainClient.getLibrary(creatorId);
      setEntries(res.entries);
      setLibrarySize(res.size);
      onLibraryChange?.(res.size);
    } catch (err) {
      console.error('[LibraryUploader] refresh failed', err);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDraggedOver(false);
    if (e.dataTransfer.files) enqueueFiles(e.dataTransfer.files);
  }

  const need = librarySize == null ? null : Math.max(0, TUNING.SIMILARITY_MIN_LIBRARY_SIZE - librarySize);
  const ready = need === 0;

  return (
    <div className="flex flex-col gap-3 rounded-md border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-baseline justify-between">
        <div className="text-xs uppercase tracking-[0.2em] text-white/55">your library</div>
        <div className="text-[10px] text-white/40">
          {librarySize == null
            ? 'loading…'
            : ready
            ? `${librarySize} clip${librarySize === 1 ? '' : 's'} · ready`
            : `${librarySize} / ${TUNING.SIMILARITY_MIN_LIBRARY_SIZE} — need ${need} more`}
        </div>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDraggedOver(true);
        }}
        onDragLeave={() => setDraggedOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed p-4 text-xs transition-colors ${
          draggedOver
            ? 'border-orange-400/60 bg-orange-400/5 text-orange-200'
            : 'border-white/15 text-white/50 hover:border-orange-400/40 hover:text-white/80'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/mp4,video/quicktime"
          className="hidden"
          multiple
          onChange={(e) => {
            if (e.target.files) enqueueFiles(e.target.files);
            e.target.value = '';
          }}
        />
        <div>drop past clips · mp4 / mov · multi-select OK</div>
        <div className="text-[10px] text-white/30">runs TRIBE + Whisper on the box</div>
      </div>

      {uploads.length > 0 && (
        <ul className="flex flex-col gap-1 text-[11px]">
          {uploads.map((u) => (
            <li key={u.id} className="flex items-center justify-between gap-2 text-white/60">
              <span className="truncate">{u.file.name}</span>
              <span
                className={
                  u.status === 'done'
                    ? 'text-emerald-300'
                    : u.status === 'error'
                    ? 'text-red-300'
                    : u.status === 'uploading'
                    ? 'text-orange-300'
                    : 'text-white/40'
                }
              >
                {u.status === 'error' ? u.message ?? 'failed' : u.status}
              </span>
            </li>
          ))}
        </ul>
      )}

      {entries.length > 0 && (
        <div className="flex flex-col gap-1 text-[11px] text-white/40">
          <div className="text-[10px] uppercase tracking-[0.2em] text-white/30">in library</div>
          <ul className="grid grid-cols-2 gap-x-3">
            {entries.slice(0, 8).map((e) => (
              <li key={e.video_id} className="truncate">
                {e.video_id}
              </li>
            ))}
            {entries.length > 8 && <li className="text-white/30">+{entries.length - 8} more</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
