import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { X } from "lucide-react";

interface Props {
  title: string;
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
  wide?: boolean;
}

export function Modal({ title, children, onClose, busy = false, wide = false }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement as HTMLElement | null;
    dialog?.showModal();
    dialog?.querySelector<HTMLInputElement>("input:not([type=checkbox])")?.focus();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className={`user-dialog ${wide ? "user-dialog-wide" : ""}`}
      aria-labelledby={titleId}
      onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}
    >
      <div className="dialog-header">
        <h3 id={titleId}>{title}</h3>
        <button className="icon-button" aria-label="Закрыть окно" disabled={busy} onClick={onClose}><X size={20} /></button>
      </div>
      {children}
    </dialog>
  );
}
