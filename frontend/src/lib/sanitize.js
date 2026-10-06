import DOMPurify from "dompurify";

/**
 * Sanitize HTML before rendering with dangerouslySetInnerHTML.
 * Removes <script>, inline event handlers (onclick=...), javascript: URLs, etc.
 * Keeps normal formatting, tables, images and inline styles used by agreements.
 */
export function sanitizeHtml(html) {
  if (!html) return "";
  return DOMPurify.sanitize(String(html), {
    USE_PROFILES: { html: true },
    ADD_ATTR: ["target"],
    FORBID_TAGS: ["script", "iframe", "object", "embed", "form"],
  });
}

export default sanitizeHtml;
