
// content-script.js — DOM-only preview scrapers for Outlook, OneDrive, Google Drive, and eFundi.
// Purpose: provide a fast local "skim" of currently open pages for instant feedback in the popup UI.
// Heavy lifting (full Playwright scan + classification) is done by the Python backend.
//
// Messages handled:
//   { type: 'VAMP_PING' }   -> { connected: true }
//   { type: 'VAMP_SCRAPE' } -> { items: [ { source, path|subject, size } ... ] }
//
// Notes:
// - Runs on pages matched by manifest.json (MV3).
// - Uses defensive selectors; capped to avoid heavy DOM work.

(function () {
  "use strict";

  // ---- Utilities ----
  function safeText(el) {
    try { return (el && (el.innerText || el.textContent) || "").trim(); }
    catch { return ""; }
  }

  function gentleScrollToBottom() {
    try {
      // Nudge virtualized lists to load
      window.scrollTo(0, document.body.scrollHeight || 0);
    } catch {}
  }

  function cappedPush(arr, obj, cap) {
    if (arr.length < cap) arr.push(obj);
  }

  // Shared Outlook selector handling ---------------------------------------------------
  const DEFAULT_OUTLOOK_SELECTORS = [
    '[data-convid]',
    '[data-conversation-id]',
    '[data-conversationid]',
    '[data-item-id]',
    '[role="listitem"][data-convid]',
    '[role="listitem"][data-conversation-id]',
    '[role="listitem"][data-item-id]',
    '[aria-label*="Message list"] [role="listitem"]',
    '[data-automation-id="messageList"] [role="option"]',
    '[data-tid="messageListContainer"] [role="option"]',
    '[data-app-section="Mail"] [role="treeitem"]',
    '[role="option"][data-convid]',
    '[role="option"][data-item-id]'
  ];

  let sharedOutlookSelectors = DEFAULT_OUTLOOK_SELECTORS.slice();
  (function preloadSharedSelectors() {
    try {
      const sharedUrl = (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.getURL)
        ? chrome.runtime.getURL("shared/outlook_selectors.json")
        : null;
      if (!sharedUrl) return;
      fetch(sharedUrl)
        .then(resp => (resp.ok ? resp.json() : null))
        .then(data => {
          if (Array.isArray(data) && data.length) {
            sharedOutlookSelectors = data.filter(Boolean);
          }
        })
        .catch(() => {});
    } catch {}
  })();

  function outlookSelectors() {
    return sharedOutlookSelectors && sharedOutlookSelectors.length
      ? sharedOutlookSelectors
      : DEFAULT_OUTLOOK_SELECTORS;
  }

  function pageHost() {
    try { return location.host || ""; } catch { return ""; }
  }

  function extractSubjectFromAria(ariaText) {
    // Enhanced Office365 aria-label parsing
    const parts = ariaText.split(",").map(s => s.trim());
    for (const part of parts) {
      const l = part.toLowerCase();
      if (part.length > 3 &&
          !l.startsWith("unread") &&
          !l.startsWith("read") &&
          !l.startsWith("flagged") &&
          !l.startsWith("not flagged") &&
          !l.startsWith("category") &&
          !l.startsWith("from") &&
          !l.includes("preview") &&
          !l.includes("message")) {
        return part;
      }
    }
    return parts[0] || "";
  }

  // ---- Outlook Office365 ----
  function scrapeOutlook() {
    const out = [];
    const seenSubjects = new Set();
    gentleScrollToBottom();

    const MAX_ITEMS = 500;
    const selectors = outlookSelectors();

    for (const selector of selectors) {
      const rows = document.querySelectorAll(selector);
      if (typeof console !== "undefined" && console.debug) {
        console.debug("VAMP Outlook selector", selector, "matched", rows.length, "nodes");
      }
      for (const row of rows) {
        let subject = "";
        let hasAttachment = false;

        // Try to extract subject from Office365 elements
        const subjectElement = row.querySelector('[data-automationid="Subject"], [role="heading"]');
        if (subjectElement) {
          subject = safeText(subjectElement);
        } else {
          // Fallback to aria-label or first text
          const aria = row.getAttribute("aria-label");
          if (aria && typeof aria === "string") {
            subject = extractSubjectFromAria(aria);
          } else {
            const txt = safeText(row);
            if (txt) subject = (txt.split("\n")[0] || "").trim();
          }
        }

        // Check for attachments in Office365
        const attachmentIndicator = row.querySelector('[data-icon-name="Attach"]');
        if (attachmentIndicator) {
          hasAttachment = true;
        }

        if (subject && subject.length > 3) {
          const hashKey = `${subject.toLowerCase()}::${row.getAttribute("data-convid") || row.getAttribute("data-item-id") || row.getAttribute("data-conversation-id") || row.getAttribute("data-conversationid") || ""}`;
          if (seenSubjects.has(hashKey)) {
            continue;
          }
          seenSubjects.add(hashKey);
          cappedPush(out, {
            source: "Outlook Office365",
            subject: hasAttachment ? `${subject} (attachment)` : subject,
            size: 0
          }, MAX_ITEMS);
        }
        if (out.length >= MAX_ITEMS) break;
      }
      if (out.length >= MAX_ITEMS) break;
    }
    return out;
  }

  // ---- OneDrive (SharePoint/Personal) ----
  function scrapeOneDrive() {
    const out = [];
    gentleScrollToBottom();

    // Common layout uses [role="row"] for listing
    const rows = document.querySelectorAll('[role="row"]');
    for (const row of rows) {
      const txt = safeText(row);
      if (!txt) continue;
      const name = (txt.split("\t")[0] || "").trim() || (txt.split("\n")[0] || "").trim();
      if (!name) continue;

      cappedPush(out, {
        source: "OneDrive",
        path: name,
        size: 0
      }, 200);
      if (out.length >= 200) break;
    }
    return out;
  }

  // ---- Google Drive ----
  function scrapeDrive() {
    const out = [];
    gentleScrollToBottom();

    // Drive list rows commonly use div[role="row"]
    const rows = document.querySelectorAll('div[role="row"]');
    for (const row of rows) {
      const txt = safeText(row);
      if (!txt) continue;
      const name = (txt.split("\t")[0] || "").trim() || (txt.split("\n")[0] || "").trim();
      if (!name) continue;

      cappedPush(out, {
        source: "Google Drive",
        path: name,
        size: 0
      }, 200);
      if (out.length >= 200) break;
    }
    return out;
  }

  // ---- eFundi (Sakai) ----
  function scrapeEFundi() {
    const out = [];
    gentleScrollToBottom();

    // Cover common containers: table/list rows, portlet bodies, instructions, resource lists
    const sels = [
      '[role="row"]',
      '.listHier',
      '.portletBody',
      '.instruction',
      '.listHier > li',
      'table.listHier tr'
    ];
    for (const sel of sels) {
      const nodes = document.querySelectorAll(sel);
      for (const el of nodes) {
        const txt = safeText(el);
        if (!txt || txt.length < 5) continue;
        const first = (txt.split("\n")[0] || "").slice(0, 160).trim();
        if (!first) continue;

        cappedPush(out, {
          source: "eFundi",
          path: first,
          size: 0
        }, 300);
        if (out.length >= 300) break;
      }
      if (out.length >= 300) break;
    }
    return out;
  }

  // ---- Router ----
  function routeScrape() {
    const host = pageHost();

    try {
      if (/outlook\.(office|live|office365)\.com$/i.test(host)) {
        return scrapeOutlook();
      }
      if (/(\.sharepoint\.com|\.my\.sharepoint\.com|files\.1drv\.com|onedrive\.live\.com)$/i.test(host)) {
        return scrapeOneDrive();
      }
      if (/drive\.google\.com$/i.test(host)) {
        return scrapeDrive();
      }
      if (/efundi\.nwu\.ac\.za$/i.test(host)) {
        return scrapeEFundi();
      }
    } catch {
      // fall-through to empty array
    }
    return [];
  }

  // ---- Message bridge (popup -> content) ----
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    try {
      if (!msg || typeof msg !== "object") return;

      if (msg.type === "VAMP_PING") {
        sendResponse && sendResponse({ connected: true });
        return;
      }

      if (msg.type === "VAMP_SCRAPE") {
        const items = routeScrape();
        sendResponse && sendResponse({ items });
        return;
      }
    } catch (e) {
      try { sendResponse && sendResponse({ items: [] }); } catch {}
    }
  });

})();