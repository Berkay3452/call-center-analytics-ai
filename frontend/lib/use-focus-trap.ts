"use client";

import { useEffect, useRef } from "react";

interface UseFocusTrapOptions {
  isOpen: boolean;
  onClose?: () => void;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
}

export function useFocusTrap<T extends HTMLElement = HTMLDivElement>({
  isOpen,
  onClose,
  returnFocusRef,
  initialFocusRef,
}: UseFocusTrapOptions) {
  const containerRef = useRef<T>(null);
  const previousActiveElementRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Modalı tetikleyen aktif elemanı kaydet
    const elementToRestore =
      returnFocusRef?.current ?? (document.activeElement as HTMLElement | null);
    previousActiveElementRef.current = elementToRestore;

    const container = containerRef.current;
    if (!container) return;

    const focusableSelectors = [
      'a[href]',
      'button:not([disabled])',
      'textarea:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(", ");

    // İlk odağı modal içine ver
    const focusInitialElement = () => {
      if (initialFocusRef?.current) {
        initialFocusRef.current.focus();
        return;
      }
      const focusables = container.querySelectorAll<HTMLElement>(focusableSelectors);
      if (focusables.length > 0) {
        focusables[0].focus();
      } else {
        container.focus();
      }
    };

    const timer = setTimeout(focusInitialElement, 20);

    const handleKeyDown = (e: KeyboardEvent) => {
      // Escape ile kapatma
      if (e.key === "Escape" && onClose) {
        e.preventDefault();
        e.stopPropagation();
        onClose();
        return;
      }

      // Focus Trap (Tab & Shift+Tab)
      if (e.key === "Tab") {
        const focusableNodes = Array.from(
          container.querySelectorAll<HTMLElement>(focusableSelectors)
        ).filter((el) => el.offsetParent !== null || el === document.activeElement);

        if (focusableNodes.length === 0) {
          e.preventDefault();
          return;
        }

        const firstElement = focusableNodes[0];
        const lastElement = focusableNodes[focusableNodes.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement || !container.contains(document.activeElement)) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement || !container.contains(document.activeElement)) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      clearTimeout(timer);
      document.removeEventListener("keydown", handleKeyDown);

      // Modal kapandığında odağı tetikleyen butona/elemana iade et
      const toFocus = elementToRestore ?? previousActiveElementRef.current;
      if (toFocus && typeof toFocus.focus === "function") {
        setTimeout(() => {
          toFocus.focus();
        }, 10);
      }
    };
  }, [isOpen, onClose, returnFocusRef, initialFocusRef]);

  return containerRef;
}
