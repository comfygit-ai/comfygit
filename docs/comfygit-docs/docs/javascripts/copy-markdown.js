// Copy Markdown Button - Copies raw markdown source to clipboard for LLM use
(function() {
  'use strict';

  const REPO_BASE = 'https://raw.githubusercontent.com/ComfyDock/comfydock/main/docs/comfydock-docs/docs/';
  const CACHE_KEY_PREFIX = 'md_cache_';

  function getCurrentPagePath() {
    const path = window.location.pathname;
    // Remove leading/trailing slashes and 'index.html' if present
    let cleaned = path.replace(/^\/+|\/+$/g, '').replace(/index\.html$/, '');

    // Handle root path
    if (!cleaned || cleaned === '') {
      return 'index.md';
    }

    // Append .md if not present
    return cleaned.endsWith('.md') ? cleaned : cleaned + '.md';
  }

  function getRawMarkdownUrl() {
    return REPO_BASE + getCurrentPagePath();
  }

  async function fetchMarkdown(url) {
    const cacheKey = CACHE_KEY_PREFIX + url;

    // Check cache first
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) {
      return cached;
    }

    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch: ${response.status}`);
    }

    const markdown = await response.text();
    sessionStorage.setItem(cacheKey, markdown);
    return markdown;
  }

  async function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
  }

  function showNotification(message, isError = false) {
    const notification = document.createElement('div');
    notification.className = 'md-copy-notification' + (isError ? ' error' : '');
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => notification.classList.add('show'), 10);
    setTimeout(() => {
      notification.classList.remove('show');
      setTimeout(() => document.body.removeChild(notification), 300);
    }, 2500);
  }

  async function handleCopyClick(button) {
    const svg = button.querySelector('svg');
    const originalSvg = svg.outerHTML;

    try {
      button.disabled = true;
      svg.outerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><circle cx="12" cy="12" r="10" opacity="0.3"/></svg>';

      const url = getRawMarkdownUrl();
      const markdown = await fetchMarkdown(url);
      await copyToClipboard(markdown);

      button.querySelector('svg').outerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/></svg>';
      showNotification('Markdown copied to clipboard!');

      setTimeout(() => {
        button.querySelector('svg').outerHTML = originalSvg;
        button.disabled = false;
      }, 1500);
    } catch (error) {
      console.error('Failed to copy markdown:', error);
      button.querySelector('svg').outerHTML = originalSvg;
      button.disabled = false;
      showNotification('Failed to copy markdown', true);
    }
  }

  function createCopyButton() {
    const button = document.createElement('button');
    button.className = 'md-copy-markdown-button';
    button.title = 'Copy page as Markdown for LLMs';
    button.setAttribute('aria-label', 'Copy page as Markdown');

    button.innerHTML = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
        <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>
      </svg>
      <span class="md-button-label">Copy page</span>
    `;

    button.addEventListener('click', () => handleCopyClick(button));
    return button;
  }

  function injectButton() {
    // Find the main h1 title
    const h1 = document.querySelector('.md-content h1');
    if (!h1) {
      setTimeout(injectButton, 100);
      return;
    }

    // Check if button already exists
    if (document.querySelector('.md-copy-markdown-button')) {
      return;
    }

    // Wrap h1 in a flex container if not already wrapped
    if (!h1.parentElement.classList.contains('md-title-wrapper')) {
      const wrapper = document.createElement('div');
      wrapper.className = 'md-title-wrapper';
      h1.parentNode.insertBefore(wrapper, h1);
      wrapper.appendChild(h1);

      const button = createCopyButton();
      wrapper.appendChild(button);
    }
  }

  // Initialize and handle instant navigation
  function init() {
    injectButton();

    // Re-inject on navigation for Material instant loading
    const observer = new MutationObserver(() => {
      if (!document.querySelector('.md-copy-markdown-button')) {
        injectButton();
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  // Support Material for MkDocs instant loading
  if (typeof document$ !== 'undefined') {
    // Material instant loading - subscribe to navigation events
    document$.subscribe(function() {
      init();
    });
  } else {
    // Fallback for non-instant loading
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }
})();
