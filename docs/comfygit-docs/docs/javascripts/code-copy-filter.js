// Smart Code Copy - Filters out prompts and output from copied code
// Based on UV's implementation
(function() {
  'use strict';

  // Exclude "Generic Prompt" and "Generic Output" spans from code copy
  // These are added by syntax highlighters for shell examples
  const excludedClasses = ["gp", "go"];

  /**
   * Clean clipboard text by removing prompt and output markers
   * @param {string} targetSelector - CSS selector for the code block
   * @returns {string} - Cleaned text ready for clipboard
   */
  function cleanupClipboardText(targetSelector) {
    const targetElement = document.querySelector(targetSelector);
    if (!targetElement) {
      return "";
    }

    // Filter out excluded elements and extract text content
    const clipboardText = Array.from(targetElement.childNodes)
      .filter(
        (node) =>
          !excludedClasses.some((className) =>
            node?.classList?.contains(className)
          )
      )
      .map((node) => node.textContent)
      .filter((s) => s !== "");

    return clipboardText.join("").trim();
  }

  /**
   * Set copy text attributes lazily using an Intersection Observer
   * This improves performance by only processing visible code blocks
   */
  function setCopyText() {
    // The `data-clipboard-text` attribute allows for customized content in the copy
    // See: https://www.npmjs.com/package/clipboard#copy-text-from-attribute
    const attr = "clipboardText";

    // Find all "copy" buttons whose target selector is a <code> element
    const elements = document.querySelectorAll(
      'button[data-clipboard-target$="code"]'
    );

    // Use Intersection Observer to only process visible elements
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        // Target in viewport that hasn't been patched yet
        if (
          entry.intersectionRatio > 0 &&
          entry.target.dataset[attr] === undefined
        ) {
          entry.target.dataset[attr] = cleanupClipboardText(
            entry.target.dataset.clipboardTarget
          );
        }
      });
    });

    elements.forEach((elt) => {
      observer.observe(elt);
    });
  }

  /**
   * Initialize when Material for MkDocs navigation occurs
   * Using the document$ observable is particularly important for instant loading
   * since it will not result in a page refresh in the browser
   *
   * See: https://squidfunk.github.io/mkdocs-material/customization/?h=javascript#additional-javascript
   */
  if (typeof document$ !== 'undefined') {
    // Material for MkDocs instant loading
    document$.subscribe(function () {
      setCopyText();
    });
  } else {
    // Fallback for non-instant loading
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', setCopyText);
    } else {
      setCopyText();
    }
  }
})();
