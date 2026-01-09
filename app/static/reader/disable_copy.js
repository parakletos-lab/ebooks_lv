(function () {
  'use strict';

  // NOTE: This is a best-effort client-side deterrent.
  // It prevents common copy interactions for anonymous and non-admin users on reader pages.

  function isMac() {
    return /Mac|iPhone|iPad|iPod/i.test(navigator.platform);
  }

  function isCopyKeyCombo(evt) {
    const key = (evt.key || '').toLowerCase();
    const code = (evt.code || '').toLowerCase();
    const ctrlOrCmd = isMac() ? evt.metaKey : evt.ctrlKey;

    // Copy/Cut/Paste/SelectAll
    if (ctrlOrCmd && (key === 'c' || key === 'x' || key === 'v' || key === 'a')) return true;

    // Insert-based legacy combos
    // Ctrl+Insert = Copy, Shift+Insert = Paste, Shift+Delete = Cut
    if (code === 'insert' && evt.ctrlKey) return true;
    if (code === 'insert' && evt.shiftKey) return true;
    if ((key === 'insert' || code === 'insert') && (evt.ctrlKey || evt.shiftKey)) return true;

    if ((key === 'delete' || code === 'delete') && evt.shiftKey) return true;

    return false;
  }

  function markBlocked(kind) {
    try {
      const key = '__ebookslvCopyBlock';
      const state = (window[key] = window[key] || { copy: 0, cut: 0, keydown: 0, contextmenu: 0 });
      if (kind in state) state[kind] += 1;
    } catch (_) {
      // ignore
    }
  }

  function stopEvent(evt) {
    try {
      evt.preventDefault();
      evt.stopPropagation();
      // stopImmediatePropagation not always present on older Event impls
      if (typeof evt.stopImmediatePropagation === 'function') evt.stopImmediatePropagation();
    } catch (_) {
      // ignore
    }
  }

  function clearSelection(doc) {
    try {
      const sel = doc.getSelection ? doc.getSelection() : null;
      if (sel && sel.removeAllRanges) sel.removeAllRanges();
    } catch (_) {
      // ignore
    }
  }

  function hardenDocument(doc) {
    if (!doc || doc.__ebookslv_no_copy_hardened) return;
    doc.__ebookslv_no_copy_hardened = true;

    // 1) Block context menu (right click)
    doc.addEventListener(
      'contextmenu',
      function (e) {
        markBlocked('contextmenu');
        stopEvent(e);
        return false;
      },
      true
    );

    // 2) Block selection start (mouse)
    doc.addEventListener(
      'selectstart',
      function (e) {
        stopEvent(e);
        return false;
      },
      true
    );

    // 3) Block drag (drag-selection / dragging text)
    doc.addEventListener(
      'dragstart',
      function (e) {
        stopEvent(e);
        return false;
      },
      true
    );

    // 4) Block copy / cut
    doc.addEventListener(
      'copy',
      function (e) {
        markBlocked('copy');
        try {
          if (e.clipboardData && typeof e.clipboardData.setData === 'function') {
            e.clipboardData.setData('text/plain', '');
            e.clipboardData.setData('text/html', '');
          }
        } catch (_) {
          // ignore
        }
        clearSelection(doc);
        stopEvent(e);
        return false;
      },
      true
    );

    doc.addEventListener(
      'cut',
      function (e) {
        markBlocked('cut');
        try {
          if (e.clipboardData && typeof e.clipboardData.setData === 'function') {
            e.clipboardData.setData('text/plain', '');
            e.clipboardData.setData('text/html', '');
          }
        } catch (_) {
          // ignore
        }
        clearSelection(doc);
        stopEvent(e);
        return false;
      },
      true
    );

    // 5) Block common keyboard shortcuts
    doc.addEventListener(
      'keydown',
      function (e) {
        if (!isCopyKeyCombo(e)) return;
        markBlocked('keydown');
        clearSelection(doc);
        stopEvent(e);
        return false;
      },
      true
    );

    // 6) If selection appears (e.g. programmatic), clear it.
    doc.addEventListener(
      'selectionchange',
      function () {
        // Keep this extremely cheap.
        try {
          const sel = doc.getSelection ? doc.getSelection() : null;
          if (sel && sel.toString && sel.toString()) {
            clearSelection(doc);
          }
        } catch (_) {
          // ignore
        }
      },
      true
    );
  }

  function hardenIframes(rootDoc) {
    const iframes = rootDoc.querySelectorAll ? rootDoc.querySelectorAll('iframe') : [];
    for (const iframe of iframes) {
      try {
        const idoc = iframe.contentDocument;
        if (idoc) {
          hardenDocument(idoc);
          // Also apply CSS class to iframe doc body for user-select
          if (idoc.body) idoc.body.classList.add('ebookslv-no-copy');
        }
      } catch (_) {
        // cross-origin; ignore
      }
    }
  }

  function hardenPdfJsLayers(rootDoc) {
    try {
      // PDF.js uses a selectable text layer.
      const layers = rootDoc.querySelectorAll('.textLayer');
      for (const layer of layers) {
        layer.classList.add('ebookslv-no-copy-textlayer');
      }
    } catch (_) {
      // ignore
    }
  }

  function install() {
    const doc = document;
    hardenDocument(doc);

    if (doc.body) {
      doc.body.classList.add('ebookslv-no-copy');
    }

    // Initial iframe harden (epub.js renders into iframes)
    hardenIframes(doc);
    hardenPdfJsLayers(doc);

    // Watch for dynamically created iframes / PDF.js layers
    try {
      const mo = new MutationObserver(function () {
        hardenIframes(doc);
        hardenPdfJsLayers(doc);
      });
      mo.observe(doc.documentElement || doc.body, { childList: true, subtree: true });
    } catch (_) {
      // ignore
    }

    // Try to hook epub.js if it exists; it can create/recreate iframe contents.
    try {
      const tryHook = function () {
        const r = window.reader;
        if (!r || !r.rendition || !r.rendition.hooks || !r.rendition.hooks.content) return false;
        if (r.__ebookslv_no_copy_hooked) return true;
        r.__ebookslv_no_copy_hooked = true;

        r.rendition.hooks.content.register(function (contents) {
          try {
            const idoc = contents && contents.document;
            if (idoc) {
              hardenDocument(idoc);
              if (idoc.body) idoc.body.classList.add('ebookslv-no-copy');
            }
          } catch (_) {
            // ignore
          }
        });
        return true;
      };

      // Poll briefly since reader may initialize after our deferred load.
      let attempts = 0;
      const timer = setInterval(function () {
        attempts += 1;
        if (tryHook() || attempts >= 40) {
          clearInterval(timer);
        }
      }, 250);
    } catch (_) {
      // ignore
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, { once: true });
  } else {
    install();
  }
})();
