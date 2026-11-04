// THE NATIVE BRIDGE. Inside the Mac app the page runs in a WKWebView: the native side owns the menu bar and every shortcut and calls
// window.appCommand("save" | "render" | "build" | "newTab" | "closeTab" | "find" | "undo" | "redo" | ...), and the page tells it the state
// (window.NATIVE.post({type:"state", ...}): the window title and the unsaved dot). In a browser there is no bridge and NATIVE is null.
(function () {
  "use strict";
  const h = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.colophon;
  window.NATIVE = h ? { post: m => h.postMessage(m) } : null;
  if (h) document.documentElement.classList.add("native");
})();
