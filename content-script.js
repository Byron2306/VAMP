
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
    gentleScrollToBottom();

    // Enhanced Office365 selectors
    const office365Selectors = [
      '[data-convid]', // Conversation items
      '[role="listitem"][data-item-id]', // Message list items
      '.ms-List-cell', // List cells
      '[data-automation-id="messageList"] [role="option"]', // Message list
      '[data-tid="messageListContainer"] div[role="button"]', // Message container
      '[data-app-section="Mail"] [role="treeitem"]' // Mail folder items
    ];

    for (const selector of office365Selectors) {
      const rows = document.querySelectorAll(selector);
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
          cappedPush(out, {
            source: "Outlook Office365",
            subject: hasAttachment ? `${subject} (attachment)` : subject,
            size: 0
          }, 200);
        }
        if (out.length >= 200) break;
      }
      if (out.length >= 200) break;
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