/**
 * Jobab Chat Chatbot Widget
 * Version: 2.2.0
 * Features: 
 * - Bidirectional AI Pause / Resume Controller (Visitor & Platform Owner / Human Agent)
 * - 1-Click "Talk to Human" / "Switch to AI" Switcher with Real-time WebSocket Sync
 * - Pre-Chat Lead Capture Form (Full Name & Phone/Email) for Real CRM Tracking
 * - Official 'marked.js' Open Source Markdown Engine (GFM tables, code blocks, lists, bold)
 * - Native OpenAI SDK & Gemini Web2API backend
 * - Shadow DOM Encapsulated & Anti-Duplication Cache
 */
(function (window, document) {
  "use strict";

  if (window.EnterpriseChatWidget) {
    return;
  }

  // --- Dynamic Loader for Official Open-Source 'marked.js' Engine ---
  function loadMarkedLibrary(apiUrl, callback) {
    if (window.marked && typeof window.marked.parse === "function") {
      callback(window.marked);
      return;
    }

    var localUrl = apiUrl.replace(/\/api\/v1\/?$/, "") + "/static/marked.min.js";
    var cdnUrl = "https://cdn.jsdelivr.net/npm/marked/marked.min.js";

    var script = document.createElement("script");
    script.src = localUrl;
    script.async = true;
    script.onload = function () {
      if (window.marked) {
        if (typeof window.marked.setOptions === "function") {
          window.marked.setOptions({ breaks: true, gfm: true });
        }
        callback(window.marked);
      }
    };
    script.onerror = function () {
      var cdnScript = document.createElement("script");
      cdnScript.src = cdnUrl;
      cdnScript.async = true;
      cdnScript.onload = function () {
        if (window.marked) {
          callback(window.marked);
        }
      };
      document.head.appendChild(cdnScript);
    };
    document.head.appendChild(script);
  }

  // Pure Fallback Markdown Parser
  function fallbackParseMarkdown(md) {
    if (!md) return "";
    var text = md
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    text = text.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, '<pre class="aiaas-pre"><code>$2</code></pre>');
    text = text.replace(/`([^`]+)`/g, '<code class="aiaas-inline-code">$1</code>');
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    text = text.replace(/^[\*\-] (.*$)/gim, '<li class="aiaas-li">$1</li>');
    text = text.replace(/(<li class="aiaas-li">[\s\S]*?<\/li>)/g, '<ul class="aiaas-ul">$1</ul>');
    text = text.replace(/\n\n+/g, '</p><p class="aiaas-p">');
    text = text.replace(/\n/g, '<br/>');
    return '<p class="aiaas-p">' + text + '</p>';
  }

  function renderMarkdown(md) {
    if (!md) return "";
    if (window.marked && typeof window.marked.parse === "function") {
      try {
        return window.marked.parse(md, { breaks: true, gfm: true });
      } catch (e) {
        console.error("Marked parse error:", e);
      }
    }
    return fallbackParseMarkdown(md);
  }

  function createWidget(config) {
    var widgetKey = config.widgetKey;
    var apiUrl = config.apiUrl || "http://127.0.0.1:8000/api/v1";
    var primaryColor = config.primaryColor || "#4F46E5";
    var position = config.position || "bottom-right";

    // Pre-Chat Lead Info
    var visitorName = localStorage.getItem("aiaas_vis_name_" + widgetKey) || "";
    var visitorContact = localStorage.getItem("aiaas_vis_contact_" + widgetKey) || "";

    var conversationId = null;
    var visitorSessionId = localStorage.getItem("aiaas_vis_sess_" + widgetKey);
    if (!visitorSessionId) {
      visitorSessionId = "vis_" + Math.random().toString(36).substring(2, 12);
      localStorage.setItem("aiaas_vis_sess_" + widgetKey, visitorSessionId);
    }

    var isOpen = false;
    var isTyping = false;
    var isAiPaused = false;
    var socket = null;
    var isWsConnected = false;
    var recentMessages = []; // Anti-duplication cache

    var widgetConfig = {
      header_title: config.headerTitle || "Live Support",
      welcome_message: "Hello! How can we assist you today?",
      primary_color: primaryColor
    };

    // Root host element
    var host = document.createElement("div");
    host.id = "aiaas-widget-host";
    document.body.appendChild(host);

    // Shadow DOM for complete CSS encapsulation
    var shadow = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;

    // Inject Modern Styles
    var style = document.createElement("style");
    style.textContent = `
      * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; }
      
      .aiaas-launcher {
        position: fixed;
        bottom: 24px;
        ${position === "bottom-left" ? "left: 24px;" : "right: 24px;"}
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: ${primaryColor};
        color: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.22);
        z-index: 9999999;
        transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.25s ease;
        border: none;
        outline: none;
      }
      .aiaas-launcher:hover {
        transform: scale(1.08);
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.3);
      }
      .aiaas-launcher svg {
        width: 28px;
        height: 28px;
        fill: currentColor;
        transition: transform 0.2s ease;
      }

      .aiaas-badge {
        position: absolute;
        top: -2px;
        right: -2px;
        width: 14px;
        height: 14px;
        background: #10B981;
        border: 2px solid #ffffff;
        border-radius: 50%;
      }

      .aiaas-window {
        position: fixed;
        bottom: 96px;
        ${position === "bottom-left" ? "left: 24px;" : "right: 24px;"}
        width: 420px;
        max-width: calc(100vw - 40px);
        height: 600px;
        max-height: calc(100vh - 120px);
        background: #ffffff;
        border-radius: 20px;
        box-shadow: 0 18px 48px rgba(0, 0, 0, 0.2);
        display: flex;
        flex-direction: column;
        overflow: hidden;
        z-index: 9999999;
        opacity: 0;
        transform: translateY(20px) scale(0.95);
        pointer-events: none;
        transition: opacity 0.25s ease, transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
        border: 1px solid rgba(0, 0, 0, 0.08);
      }

      .aiaas-window.open {
        opacity: 1;
        transform: translateY(0) scale(1);
        pointer-events: auto;
      }

      .aiaas-header {
        padding: 14px 18px;
        background: ${primaryColor};
        color: #ffffff;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      }

      .aiaas-header-title {
        font-size: 15px;
        font-weight: 700;
        letter-spacing: -0.2px;
      }

      .aiaas-header-status {
        font-size: 11px;
        opacity: 0.9;
        display: flex;
        align-items: center;
        gap: 6px;
        margin-top: 2px;
      }

      .aiaas-status-dot {
        width: 7px;
        height: 7px;
        background: #34D399;
        border-radius: 50%;
        display: inline-block;
      }

      .aiaas-header-actions {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .aiaas-handover-btn {
        background: rgba(255, 255, 255, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.35);
        color: #ffffff;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.2s, transform 0.1s;
        display: flex;
        align-items: center;
        gap: 4px;
        outline: none;
      }
      .aiaas-handover-btn:hover {
        background: rgba(255, 255, 255, 0.35);
        transform: scale(1.02);
      }

      .aiaas-cart-btn {
        background: rgba(255, 255, 255, 0.2);
        border: none;
        color: #ffffff;
        padding: 5px 9px;
        border-radius: 20px;
        display: flex;
        align-items: center;
        gap: 4px;
        cursor: pointer;
        font-size: 11px;
        font-weight: 700;
        transition: background 0.2s, transform 0.1s;
        position: relative;
        outline: none;
      }
      .aiaas-cart-btn:hover {
        background: rgba(255, 255, 255, 0.35);
        transform: scale(1.02);
      }
      .aiaas-cart-badge {
        background: #10B981;
        color: #ffffff;
        font-size: 10px;
        font-weight: 800;
        padding: 1px 5px;
        border-radius: 10px;
        min-width: 14px;
        text-align: center;
      }

      .aiaas-close-btn {
        background: rgba(255, 255, 255, 0.2);
        border: none;
        color: #ffffff;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        font-size: 14px;
        transition: background 0.2s;
      }
      .aiaas-close-btn:hover {
        background: rgba(255, 255, 255, 0.35);
      }

      /* Pre-Chat Lead Capture Form */
      .aiaas-prechat {
        flex: 1;
        padding: 24px;
        background: #F8FAFC;
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 16px;
      }
      .aiaas-prechat-badge {
        font-size: 11px;
        font-weight: 700;
        color: ${primaryColor};
        background: rgba(79, 70, 229, 0.08);
        padding: 4px 10px;
        border-radius: 20px;
        width: fit-content;
      }
      .aiaas-prechat-title {
        font-size: 18px;
        font-weight: 800;
        color: #0F172A;
        letter-spacing: -0.3px;
      }
      .aiaas-prechat-sub {
        font-size: 12px;
        color: #64748B;
        line-height: 1.4;
      }
      .aiaas-field {
        display: flex;
        flex-direction: column;
        gap: 5px;
      }
      .aiaas-field label {
        font-size: 11.5px;
        font-weight: 600;
        color: #334155;
      }
      .aiaas-field input {
        width: 100%;
        padding: 10px 14px;
        border-radius: 12px;
        border: 1px solid #CBD5E1;
        font-size: 13px;
        background: #ffffff;
        outline: none;
        transition: border 0.2s;
      }
      .aiaas-field input:focus {
        border-color: ${primaryColor};
      }
      .aiaas-start-btn {
        margin-top: 6px;
        padding: 12px;
        background: ${primaryColor};
        color: #ffffff;
        border: none;
        border-radius: 14px;
        font-size: 13px;
        font-weight: 700;
        cursor: pointer;
        transition: opacity 0.2s, transform 0.1s;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
      }
      .aiaas-start-btn:hover {
        opacity: 0.92;
        transform: translateY(-1px);
      }

      .aiaas-messages {
        flex: 1;
        padding: 18px;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 12px;
        background: #F8FAFC;
      }

      .aiaas-msg {
        max-width: 90%;
        padding: 12px 16px;
        font-size: 13.5px;
        line-height: 1.55;
        border-radius: 16px;
        word-wrap: break-word;
        animation: aiaasFadeIn 0.2s ease;
      }

      @keyframes aiaasFadeIn {
        from { opacity: 0; transform: translateY(6px); }
        to { opacity: 1; transform: translateY(0); }
      }

      .aiaas-msg.visitor {
        align-self: flex-end;
        background: ${primaryColor};
        color: #ffffff;
        border-bottom-right-radius: 4px;
      }

      .aiaas-msg.ai {
        align-self: flex-start;
        background: #ffffff;
        color: #1E293B;
        border: 1px solid #E2E8F0;
        border-bottom-left-radius: 4px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
      }

      .aiaas-msg.agent {
        align-self: flex-start;
        background: #EEF2FF;
        color: #312E81;
        border: 1px solid #C7D2FE;
        border-bottom-left-radius: 4px;
      }

      .aiaas-msg.system {
        align-self: center;
        background: #FEF3C7;
        color: #92400E;
        font-size: 11.5px;
        padding: 6px 12px;
        border-radius: 20px;
        border: 1px solid #FDE68A;
      }

      .aiaas-msg-author {
        font-size: 10.5px;
        font-weight: 700;
        margin-bottom: 5px;
        color: ${primaryColor};
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .aiaas-msg-meta {
        font-size: 10px;
        margin-top: 5px;
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 3px;
        line-height: 1;
        opacity: 0.82;
      }
      .aiaas-msg.visitor .aiaas-msg-meta {
        color: rgba(255, 255, 255, 0.88);
      }
      .aiaas-msg.ai .aiaas-msg-meta {
        color: #94A3B8;
      }
      .aiaas-msg.agent .aiaas-msg-meta {
        color: #6366F1;
      }
      .aiaas-msg-check {
        font-size: 10px;
        color: #A7F3D0;
        font-weight: 700;
        margin-left: 2px;
      }

      /* Pure Open-Source Markdown (marked.js) Typography Styles */
      .aiaas-msg-body p { margin: 0 0 8px 0; }
      .aiaas-msg-body p:last-child { margin-bottom: 0; }
      .aiaas-msg-body strong { font-weight: 700; color: inherit; }
      .aiaas-msg-body em { font-style: italic; }
      .aiaas-msg-body h1, .aiaas-msg-body h2, .aiaas-msg-body h3, .aiaas-msg-body h4 {
        font-weight: 750;
        margin: 10px 0 6px 0;
        line-height: 1.3;
        color: inherit;
      }
      .aiaas-msg-body h1 { font-size: 16px; }
      .aiaas-msg-body h2 { font-size: 15px; }
      .aiaas-msg-body h3 { font-size: 14px; }
      .aiaas-msg-body h4 { font-size: 13.5px; }

      .aiaas-msg-body ul, .aiaas-msg-body ol { margin: 6px 0 8px 18px; padding: 0; }
      .aiaas-msg-body li { margin-bottom: 4px; line-height: 1.45; }

      .aiaas-msg-body blockquote {
        border-left: 3px solid ${primaryColor};
        padding: 4px 0 4px 10px;
        margin: 8px 0;
        color: #64748B;
        background: rgba(0,0,0,0.02);
        border-radius: 0 6px 6px 0;
      }

      .aiaas-msg-body a { color: #4F46E5; text-decoration: underline; font-weight: 600; }
      .aiaas-msg-body code {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 12px;
        background: #F1F5F9;
        color: #0F172A;
        padding: 2px 6px;
        border-radius: 6px;
        border: 1px solid #E2E8F0;
      }
      .aiaas-msg.visitor code {
        background: rgba(255, 255, 255, 0.2);
        color: #ffffff;
        border-color: rgba(255, 255, 255, 0.3);
      }

      .aiaas-msg-body pre {
        margin: 8px 0;
        border-radius: 10px;
        overflow-x: auto;
        background: #0F172A;
        color: #E2E8F0;
        padding: 12px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 12px;
        line-height: 1.45;
        border: 1px solid #1E293B;
      }
      .aiaas-msg-body pre code { background: transparent; color: inherit; border: none; padding: 0; }

      /* Markdown Tables */
      .aiaas-msg-body table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 12px; }
      .aiaas-msg-body th, .aiaas-msg-body td { border: 1px solid #E2E8F0; padding: 6px 10px; text-align: left; }
      .aiaas-msg-body th { background: #F8FAFC; font-weight: 700; }

      .aiaas-typing {
        display: flex;
        gap: 4px;
        padding: 10px 14px;
        background: #ffffff;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        width: fit-content;
        align-self: flex-start;
      }

      .aiaas-dot {
        width: 6px;
        height: 6px;
        background: #94A3B8;
        border-radius: 50%;
        animation: aiaasBounce 1.4s infinite ease-in-out;
      }
      .aiaas-dot:nth-child(1) { animation-delay: -0.32s; }
      .aiaas-dot:nth-child(2) { animation-delay: -0.16s; }

      @keyframes aiaasBounce {
        0%, 80%, 100% { transform: scale(0); }
        40% { transform: scale(1); }
      }

      .aiaas-footer {
        padding: 12px 16px;
        background: #ffffff;
        border-top: 1px solid #E2E8F0;
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .aiaas-input {
        flex: 1;
        border: 1px solid #CBD5E1;
        border-radius: 24px;
        padding: 10px 16px;
        font-size: 13px;
        outline: none;
        transition: border 0.2s;
      }
      .aiaas-input:focus { border-color: ${primaryColor}; }

      .aiaas-send-btn {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: ${primaryColor};
        color: #ffffff;
        border: none;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: background 0.2s, transform 0.1s;
      }
      .aiaas-send-btn:hover { opacity: 0.9; transform: scale(1.05); }

      .aiaas-quick-chips {
        display: flex;
        gap: 6px;
        padding: 6px 14px;
        background: #F8FAFC;
        border-top: 1px solid #E2E8F0;
        overflow-x: auto;
        white-space: nowrap;
      }
      .aiaas-chip {
        background: #ffffff;
        border: 1px solid #CBD5E1;
        color: #334155;
        font-size: 11px;
        font-weight: 600;
        padding: 4px 10px;
        border-radius: 14px;
        cursor: pointer;
        transition: all 0.15s;
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }
      .aiaas-chip:hover {
        background: ${primaryColor};
        color: #ffffff;
        border-color: ${primaryColor};
        transform: translateY(-1px);
      }

      /* In-Chat Product Cards */
      .aiaas-prod-container {
        display: flex;
        flex-direction: column;
        gap: 10px;
        margin-top: 8px;
        width: 100%;
      }
      .aiaas-prod-container.scrollable {
        max-height: 385px;
        overflow-y: auto;
        overflow-x: hidden;
        padding-right: 4px;
        scroll-behavior: smooth;
      }
      .aiaas-prod-container.scrollable::-webkit-scrollbar {
        width: 5px;
      }
      .aiaas-prod-container.scrollable::-webkit-scrollbar-track {
        background: rgba(0, 0, 0, 0.03);
        border-radius: 4px;
      }
      .aiaas-prod-container.scrollable::-webkit-scrollbar-thumb {
        background: #CBD5E1;
        border-radius: 4px;
      }
      .aiaas-prod-container.scrollable::-webkit-scrollbar-thumb:hover {
        background: #94A3B8;
      }
      .aiaas-prod-scroll-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-size: 11px;
        font-weight: 700;
        color: #475569;
        padding: 5px 8px;
        background: #F8FAFC;
        border: 1px dashed #CBD5E1;
        border-radius: 8px;
        margin-bottom: 2px;
        position: sticky;
        top: 0;
        z-index: 2;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
      }
      /* Order Tracking Card */
      .aiaas-track-card {
        background: #ffffff;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 12px 14px;
        display: flex;
        flex-direction: column;
        gap: 10px;
        box-shadow: 0 3px 12px rgba(0,0,0,0.05);
        margin-top: 8px;
        width: 100%;
        box-sizing: border-box;
      }
      .aiaas-track-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 8px;
        border-bottom: 1px solid #F1F5F9;
      }
      .aiaas-track-badge {
        font-size: 9.5px;
        font-weight: 800;
        text-transform: uppercase;
        padding: 2px 7px;
        border-radius: 6px;
      }
      .aiaas-track-badge.pending { background: #FEF3C7; color: #D97706; border: 1px solid #FDE68A; }
      .aiaas-track-badge.confirmed { background: #E0E7FF; color: #4338CA; border: 1px solid #C7D2FE; }
      .aiaas-track-badge.shipped { background: #E0F2FE; color: #0369A1; border: 1px solid #BAE6FD; }
      .aiaas-track-badge.delivered { background: #ECFDF5; color: #059669; border: 1px solid #A7F3D0; }
      .aiaas-track-badge.cancelled { background: #FEE2E2; color: #DC2626; border: 1px solid #FECACA; }

      .aiaas-stepper-wrap {
        display: flex;
        align-items: center;
        justify-content: space-between;
        position: relative;
        margin: 6px 0;
      }
      .aiaas-stepper-step {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 3px;
        z-index: 2;
      }
      .aiaas-step-dot {
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: #E2E8F0;
        color: #64748B;
        font-size: 9px;
        font-weight: 800;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 2px solid #ffffff;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      }
      .aiaas-step-dot.active {
        background: #059669;
        color: #ffffff;
      }
      .aiaas-step-dot.current {
        background: #059669;
        color: #ffffff;
        box-shadow: 0 0 0 3px rgba(5, 150, 105, 0.2);
        animation: aiaas-pulse-dot 1.5s infinite;
      }
      .aiaas-step-label {
        font-size: 9.5px;
        font-weight: 700;
        color: #64748B;
      }
      .aiaas-step-label.active {
        color: #0F172A;
      }
      @keyframes aiaas-pulse-dot {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.15); }
      }
      .aiaas-prod-card {
        background: #ffffff;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 12px;
        display: flex;
        flex-direction: column;
        gap: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        transition: transform 0.15s, border-color 0.15s;
      }
      .aiaas-prod-card:hover {
        border-color: #CBD5E1;
        transform: translateY(-1px);
      }
      .aiaas-prod-header {
        display: flex;
        align-items: center;
        gap: 10px;
      }
      .aiaas-prod-img {
        width: 52px;
        height: 52px;
        border-radius: 10px;
        object-fit: cover;
        background: #F1F5F9;
        flex-shrink: 0;
      }
      .aiaas-prod-info {
        flex: 1;
        min-width: 0;
      }
      .aiaas-prod-title {
        font-size: 12.5px;
        font-weight: 750;
        color: #0F172A;
        line-height: 1.35;
      }
      .aiaas-prod-price {
        font-size: 13px;
        font-weight: 800;
        color: #059669;
        margin-top: 3px;
      }
      .aiaas-prod-variants {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        color: #64748B;
        flex-wrap: wrap;
      }
      .aiaas-variant-chip {
        padding: 2px 8px;
        border-radius: 6px;
        border: 1px solid #CBD5E1;
        background: #F8FAFC;
        cursor: pointer;
        font-size: 10px;
        font-weight: 700;
        color: #334155;
        transition: all 0.15s;
      }
      .aiaas-variant-chip.active {
        background: ${primaryColor};
        color: #ffffff;
        border-color: ${primaryColor};
      }
      .aiaas-prod-bottom-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        padding-top: 8px;
        border-top: 1px solid #F1F5F9;
      }
      .aiaas-qty-picker {
        display: flex;
        align-items: center;
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        overflow: hidden;
        background: #F8FAFC;
      }
      .aiaas-qty-btn {
        background: transparent;
        border: none;
        width: 26px;
        height: 26px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 13px;
        font-weight: 800;
        color: #334155;
        cursor: pointer;
        transition: background 0.15s;
      }
      .aiaas-qty-btn:hover {
        background: #E2E8F0;
      }
      .aiaas-qty-val {
        width: 24px;
        text-align: center;
        font-size: 12px;
        font-weight: 800;
        color: #0F172A;
      }
      .aiaas-btn-actions {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .aiaas-btn-add-cart {
        background: #F1F5F9;
        color: #1E293B;
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 11px;
        font-weight: 700;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 4px;
        transition: all 0.15s;
      }
      .aiaas-btn-add-cart:hover {
        background: #E2E8F0;
        border-color: #94A3B8;
      }
      .aiaas-prod-buy-btn {
        background: #059669;
        color: #ffffff;
        border: none;
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 11px;
        font-weight: 700;
        cursor: pointer;
        transition: opacity 0.15s, transform 0.1s;
        flex-shrink: 0;
      }
      .aiaas-prod-buy-btn:hover {
        opacity: 0.92;
        transform: translateY(-1px);
      }

      /* Floating Bottom Cart Bar */
      .aiaas-cart-bar {
        background: #0F172A;
        color: #ffffff;
        padding: 10px 14px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-top: 1px solid #334155;
        box-shadow: 0 -4px 12px rgba(0,0,0,0.1);
        animation: aiaasSlideUp 0.2s ease-out;
      }
      .aiaas-cart-bar-info {
        display: flex;
        flex-direction: column;
        gap: 1px;
      }
      .aiaas-cart-bar-count {
        font-size: 11px;
        color: #94A3B8;
        font-weight: 600;
      }
      .aiaas-cart-bar-total {
        font-size: 13px;
        font-weight: 800;
        color: #34D399;
      }
      .aiaas-cart-bar-btn {
        background: #059669;
        color: #ffffff;
        border: none;
        border-radius: 10px;
        padding: 7px 12px;
        font-size: 11.5px;
        font-weight: 700;
        cursor: pointer;
        transition: opacity 0.15s, transform 0.1s;
      }
      .aiaas-cart-bar-btn:hover {
        opacity: 0.92;
        transform: scale(1.02);
      }

      /* bKash Payment Pending Interactive Card */
      .aiaas-pay-action-card {
        background: #FDF2F8;
        border: 1.5px solid #FBCFE8;
        border-radius: 14px;
        padding: 12px 14px;
        margin-top: 8px;
        box-shadow: 0 4px 12px rgba(226, 19, 110, 0.08);
      }
      .aiaas-pay-action-title {
        font-size: 13px;
        font-weight: 800;
        color: #9D174D;
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 4px;
      }
      .aiaas-pay-action-desc {
        font-size: 11.5px;
        color: #831843;
        line-height: 1.4;
        margin-bottom: 10px;
      }
      .aiaas-pay-btn-group {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .aiaas-btn-reopen-bkash {
        background: #E2136E;
        color: #ffffff;
        border: none;
        border-radius: 10px;
        padding: 8px 12px;
        font-size: 12px;
        font-weight: 700;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        transition: transform 0.15s, opacity 0.15s;
        box-shadow: 0 2px 8px rgba(226, 19, 110, 0.25);
      }
      .aiaas-btn-reopen-bkash:hover {
        opacity: 0.95;
        transform: translateY(-1px);
      }
      .aiaas-btn-switch-cod {
        background: #ffffff;
        color: #374151;
        border: 1px solid #D1D5DB;
        border-radius: 10px;
        padding: 7px 12px;
        font-size: 11.5px;
        font-weight: 600;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        transition: background 0.15s;
      }
      .aiaas-btn-switch-cod:hover {
        background: #F3F4F6;
        color: #111827;
      }

      /* In-Widget 1-Click Checkout Drawer */
      .aiaas-checkout-drawer {
        position: absolute;
        inset: 0;
        background: #ffffff;
        z-index: 50;
        display: none;
        flex-direction: column;
        padding: 18px;
        overflow-y: auto;
        animation: aiaasSlideUp 0.25s ease-out;
      }
      .aiaas-checkout-drawer.open {
        display: flex;
      }
      @keyframes aiaasSlideUp {
        from { transform: translateY(100%); }
        to { transform: translateY(0); }
      }
      .aiaas-checkout-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid #E2E8F0;
        padding-bottom: 10px;
        margin-bottom: 12px;
      }
      .aiaas-checkout-title {
        font-size: 15px;
        font-weight: 800;
        color: #0F172A;
      }

      /* Cart Items in Checkout Drawer */
      .aiaas-cart-item-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        padding: 10px 0;
        border-bottom: 1px solid #F1F5F9;
      }
      .aiaas-cart-item-info {
        display: flex;
        align-items: center;
        gap: 8px;
        flex: 1;
        min-width: 0;
      }
      .aiaas-cart-item-img {
        width: 40px;
        height: 40px;
        border-radius: 8px;
        object-fit: cover;
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        flex-shrink: 0;
      }
      .aiaas-cart-item-title {
        font-size: 12px;
        font-weight: 700;
        color: #0F172A;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .aiaas-cart-item-meta {
        font-size: 11px;
        color: #64748B;
        margin-top: 2px;
      }
      .aiaas-cart-item-remove {
        background: transparent;
        border: none;
        color: #EF4444;
        cursor: pointer;
        padding: 4px;
        font-size: 14px;
        transition: opacity 0.15s;
      }
      .aiaas-cart-item-remove:hover {
        opacity: 0.7;
      }

      .aiaas-powered {
        text-align: center;
        font-size: 10px;
        color: #94A3B8;
        padding: 4px 0 6px 0;
        background: #ffffff;
      }
    `;
    shadow.appendChild(style);

    // Launcher Button
    var launcher = document.createElement("button");
    launcher.className = "aiaas-launcher";
    launcher.innerHTML = `
      <svg viewBox="0 0 24 24">
        <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/>
      </svg>
      <div class="aiaas-badge"></div>
    `;
    shadow.appendChild(launcher);

    // Chat Window
    var win = document.createElement("div");
    win.className = "aiaas-window";
    win.innerHTML = `
      <div class="aiaas-header">
        <div>
          <div class="aiaas-header-title">${widgetConfig.header_title}</div>
          <div class="aiaas-header-status">
            <span class="aiaas-status-dot"></span> <span id="aiaas-status-txt">AI Active</span>
          </div>
        </div>
        <div class="aiaas-header-actions">
          <button class="aiaas-cart-btn" id="aiaas-btn-header-cart" title="View Shopping Cart" style="display:none;">
            🛒 <span class="aiaas-cart-badge" id="aiaas-cart-badge" style="display:none;">0</span>
          </button>
          <button class="aiaas-handover-btn" id="aiaas-btn-handover">👤 Talk to Human</button>
          <button class="aiaas-close-btn">✕</button>
        </div>
      </div>

      <!-- Pre-Chat Lead Capture Screen -->
      <div class="aiaas-prechat" style="display: ${visitorName ? 'none' : 'flex'};">
        <div class="aiaas-prechat-badge">👋 Start a Conversation</div>
        <div class="aiaas-prechat-title">Welcome to Live Support!</div>
        <div class="aiaas-prechat-sub">Please introduce yourself so our support team can best assist you.</div>
        
        <div class="aiaas-field">
          <label>Your Full Name *</label>
          <input type="text" id="aiaas-inp-name" placeholder="e.g. Farhan Rahman" />
        </div>
        <div class="aiaas-field">
          <label>Phone or Email Address *</label>
          <input type="text" id="aiaas-inp-contact" placeholder="e.g. 01712345678 or farhan@example.com" />
        </div>

        <button class="aiaas-start-btn" id="aiaas-btn-start">
          Start Chatting ➔
        </button>
      </div>

      <!-- Active Message Thread -->
      <div class="aiaas-messages" style="display: ${visitorName ? 'flex' : 'none'};"></div>

      <!-- Adaptive Quick Action Chips (Dynamically Rendered for E-Com vs ERP) -->
      <div class="aiaas-quick-chips" style="display: ${visitorName ? 'flex' : 'none'};"></div>

      <!-- Sticky Bottom Cart Summary Bar (appears when items are in cart) -->
      <div class="aiaas-cart-bar" id="aiaas-cart-bar" style="display:none;">
        <div class="aiaas-cart-bar-info">
          <span class="aiaas-cart-bar-count">🛒 <b id="aiaas-bar-count">0</b> items in cart</span>
          <span class="aiaas-cart-bar-total" id="aiaas-bar-total">৳0 BDT</span>
        </div>
        <button class="aiaas-cart-bar-btn" id="aiaas-btn-bar-checkout">View Cart & Checkout ➔</button>
      </div>

      <!-- Composer Footer -->
      <div class="aiaas-footer" style="display: ${visitorName ? 'flex' : 'none'};">
        <input type="text" class="aiaas-input" placeholder="Type your message..." />
        <button class="aiaas-send-btn">
          <svg style="width:16px;height:16px;fill:currentColor;" viewBox="0 0 24 24">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
          </svg>
        </button>
      </div>
      <div class="aiaas-powered">⚡ Powered by N.I. BIZ Soft</div>

      <!-- In-Widget Multi-Item Shopping Cart & Checkout Drawer -->
      <div class="aiaas-checkout-drawer" id="aiaas-checkout-modal">
        <div class="aiaas-checkout-header">
          <div class="aiaas-checkout-title">🛍️ Shopping Cart & Checkout (<span id="aiaas-chk-cart-count">0</span>)</div>
          <button class="aiaas-close-btn" style="background:#E2E8F0;color:#0F172A;" id="aiaas-btn-close-checkout">✕</button>
        </div>

        <div style="font-size:11px;font-weight:700;color:#64748B;text-transform:uppercase;margin-bottom:6px;">Items in Your Cart</div>
        <div id="aiaas-checkout-items-list" style="background:#F8FAFC;padding:8px 12px;border-radius:12px;border:1px solid #E2E8F0;margin-bottom:12px;max-height:160px;overflow-y:auto;"></div>

        <div style="background:#F1F5F9;padding:10px 12px;border-radius:12px;margin-bottom:12px;font-size:11.5px;display:flex;flex-direction:column;gap:3px;">
          <div style="display:flex;justify-content:space-between;color:#64748B;">
            <span>Products Subtotal:</span>
            <strong style="color:#0F172A;" id="aiaas-chk-subtotal">৳0 BDT</strong>
          </div>
          <div style="display:flex;justify-content:space-between;color:#64748B;">
            <span>Estimated Delivery Fee:</span>
            <strong style="color:#0F172A;" id="aiaas-chk-delivery-fee">৳60 BDT</strong>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:13px;font-weight:800;color:#0F172A;padding-top:4px;border-top:1px solid #CBD5E1;margin-top:2px;">
            <span>Total Payable:</span>
            <span style="color:#059669;" id="aiaas-chk-total">৳0 BDT</span>
          </div>
        </div>
        
        <div class="aiaas-field" style="margin-bottom:10px;">
          <label>Your Full Name *</label>
          <input type="text" id="aiaas-chk-name" placeholder="Full name" />
        </div>
        <div class="aiaas-field" style="margin-bottom:10px;">
          <label>Phone Number (for Order & SMS) *</label>
          <input type="text" id="aiaas-chk-phone" placeholder="017xxxxxxxx" />
        </div>
        <div class="aiaas-field" style="margin-bottom:10px;">
          <label>Delivery Address *</label>
          <input type="text" id="aiaas-chk-address" placeholder="House, Road, Area..." />
        </div>
        <div class="aiaas-field" style="margin-bottom:10px;">
          <label>City & Delivery Fee</label>
          <select id="aiaas-chk-city" style="width:100%;padding:10px;border-radius:12px;border:1px solid #CBD5E1;font-size:13px;background:#ffffff;">
            <option value="Dhaka">Inside Dhaka (৳60 Delivery)</option>
            <option value="Chittagong">Chittagong (৳120 Delivery)</option>
            <option value="Sylhet">Sylhet (৳120 Delivery)</option>
            <option value="Rajshahi">Rajshahi (৳120 Delivery)</option>
            <option value="Khulna">Khulna (৳120 Delivery)</option>
            <option value="Barisal">Barisal (৳120 Delivery)</option>
            <option value="Rangpur">Rangpur (৳120 Delivery)</option>
            <option value="Mymensingh">Mymensingh (৳120 Delivery)</option>
            <option value="Other">Other City / District (৳120 Delivery)</option>
          </select>
        </div>
        <div class="aiaas-field" style="margin-bottom:14px;">
          <label>Payment Method</label>
          <select id="aiaas-chk-payment" style="width:100%;padding:10px;border-radius:12px;border:1px solid #CBD5E1;font-size:13px;background:#ffffff;">
            <option value="cash_on_delivery">💵 Cash on Delivery (COD)</option>
            <option value="bkash">📱 bKash Online Payment</option>
          </select>
        </div>

        <button class="aiaas-start-btn" id="aiaas-btn-submit-order" style="background:#059669;">
          Confirm Order ➔
        </button>
      </div>
    `;
    shadow.appendChild(win);

    var prechatBox = win.querySelector(".aiaas-prechat");
    var nameInp = win.querySelector("#aiaas-inp-name");
    var contactInp = win.querySelector("#aiaas-inp-contact");
    var startBtn = win.querySelector("#aiaas-btn-start");
    var handoverBtn = win.querySelector("#aiaas-btn-handover");
    var btnHeaderCart = win.querySelector("#aiaas-btn-header-cart");
    var statusTxt = win.querySelector("#aiaas-status-txt");

    var messagesBox = win.querySelector(".aiaas-messages");
    var chipsBox = win.querySelector(".aiaas-quick-chips");

    var cartBar = win.querySelector("#aiaas-cart-bar");
    var btnBarCheckout = win.querySelector("#aiaas-btn-bar-checkout");

    var checkoutModal = win.querySelector("#aiaas-checkout-modal");
    var btnCloseCheckout = win.querySelector("#aiaas-btn-close-checkout");
    var btnSubmitOrder = win.querySelector("#aiaas-btn-submit-order");
    var chkItemsList = win.querySelector("#aiaas-checkout-items-list");
    var chkName = win.querySelector("#aiaas-chk-name");
    var chkPhone = win.querySelector("#aiaas-chk-phone");
    var chkAddress = win.querySelector("#aiaas-chk-address");
    var chkCity = win.querySelector("#aiaas-chk-city");
    var chkPayment = win.querySelector("#aiaas-chk-payment");

    // Adaptive Business Model & Archetype Flags
    var isEcomEnabled = false;
    var currentBusinessCategory = "ecommerce";

    function renderAdaptiveChips(category, isEcom) {
      if (!chipsBox) return;
      chipsBox.innerHTML = "";

      var chips = [];
      if (category === "erp") {
        chips = [
          { text: "📅 Book Live Demo", query: "আমাদের ফ্যাক্টরির জন্য একটি লাইভ ডেমো শিডিউল করতে চাই" },
          { text: "🎫 Open SLA Ticket", query: "আমাদের ব্যাংক রিকনসিলিয়েশন ও Mushak 6.3 ভ্যাটে এরর আসছে, আর্জেন্ট সাপোর্ট টিকেট দরকার" },
          { text: "💰 Pricing & Plans", query: "Apex ERP এর মাসিক প্রাইসিং কত এবং কি কি প্যাকেজ আছে?" },
          { text: "👤 Talk to Specialist", action: "handover" }
        ];
      } else if (category === "services") {
        chips = [
          { text: "📅 Book Consultation", query: "আমি একটি কনসালটেশন শিডিউল করতে চাই" },
          { text: "💼 Our Services", query: "আপনাদের সার্ভিস ও প্যাকেজ সম্পর্কে জানতে চাই" },
          { text: "👤 Talk to Consultant", action: "handover" }
        ];
      } else {
        // E-Commerce
        chips = [
          { text: "🛍️ Browse Products", action: "browse" },
          { text: "📦 Track Order", query: "আমার অর্ডার ট্র্যাক করতে চাই" },
          { text: "👤 Support Agent", action: "handover" }
        ];
      }

      chips.forEach(function (c) {
        var btn = document.createElement("button");
        btn.className = "aiaas-chip";
        btn.textContent = c.text;
        btn.addEventListener("click", function () {
          if (c.action === "browse") {
            loadAndRenderProducts();
          } else if (c.action === "handover") {
            handoverBtn.click();
          } else if (c.query) {
            inputEl.value = c.query;
            sendMessage();
          }
        });
        chipsBox.appendChild(btn);
      });
    }

    // Cart State Engine (Persistent in visitor localStorage)
    var cartItems = [];

    function loadCart() {
      if (!isEcomEnabled) return;
      try {
        var raw = localStorage.getItem("aiaas_cart_" + widgetKey);
        if (raw) {
          cartItems = JSON.parse(raw) || [];
        }
      } catch (e) {
        cartItems = [];
      }
      updateCartBadges();
    }

    function saveCart() {
      if (!isEcomEnabled) return;
      try {
        localStorage.setItem("aiaas_cart_" + widgetKey, JSON.stringify(cartItems));
      } catch (e) { }
      updateCartBadges();
      renderCartDrawer();
    }

    function getCartSubtotal() {
      return cartItems.reduce(function (sum, item) {
        return sum + ((item.selling_price || item.price || 0) * (item.quantity || 1));
      }, 0);
    }

    function getCartCount() {
      return cartItems.reduce(function (sum, item) {
        return sum + (item.quantity || 1);
      }, 0);
    }

    function showCartToast(msg) {
      var existingToast = win.querySelector(".aiaas-cart-toast");
      if (existingToast) existingToast.remove();

      var toast = document.createElement("div");
      toast.className = "aiaas-cart-toast";
      toast.innerHTML = msg;
      win.appendChild(toast);
      setTimeout(function () {
        toast.remove();
      }, 2200);
    }

    function addToCart(product, qty, size, color) {
      qty = Math.max(1, parseInt(qty) || 1);
      var existing = cartItems.find(function (i) {
        return i.id === product.id && i.selected_size === size && i.selected_color === color;
      });
      if (existing) {
        existing.quantity += qty;
      } else {
        cartItems.push({
          id: product.id,
          title: product.title,
          selling_price: product.selling_price || product.unit_price,
          quantity: qty,
          selected_size: size || null,
          selected_color: color || null,
          image_url: (product.images && product.images[0]) || ""
        });
      }
      saveCart();
      showCartToast(`Added ${qty}x "${product.title}" to cart! 🛒`);
    }

    function updateCartQty(index, delta) {
      if (index >= 0 && index < cartItems.length) {
        cartItems[index].quantity += delta;
        if (cartItems[index].quantity <= 0) {
          cartItems.splice(index, 1);
        }
        saveCart();
      }
    }

    function removeFromCart(index) {
      if (index >= 0 && index < cartItems.length) {
        cartItems.splice(index, 1);
        saveCart();
      }
    }

    function clearCart() {
      cartItems = [];
      saveCart();
    }

    function updateCartBadges() {
      if (!isEcomEnabled) {
        if (cartBar) cartBar.style.display = "none";
        return;
      }
      var count = getCartCount();
      var subtotal = getCartSubtotal();

      var cartBadge = win.querySelector("#aiaas-cart-badge");
      var barCount = win.querySelector("#aiaas-bar-count");
      var barTotal = win.querySelector("#aiaas-bar-total");

      if (cartBadge) {
        if (count > 0) {
          cartBadge.textContent = count;
          cartBadge.style.display = "inline-block";
        } else {
          cartBadge.style.display = "none";
        }
      }

      if (cartBar) {
        if (count > 0 && visitorName) {
          cartBar.style.display = "flex";
          if (barCount) barCount.textContent = count;
          if (barTotal) barTotal.textContent = "৳" + subtotal.toLocaleString() + " BDT";
        } else {
          cartBar.style.display = "none";
        }
      }
    }

    function renderCartDrawer() {
      var itemsContainer = win.querySelector("#aiaas-checkout-items-list");
      var subtotalEl = win.querySelector("#aiaas-chk-subtotal");
      var deliveryFeeEl = win.querySelector("#aiaas-chk-delivery-fee");
      var totalEl = win.querySelector("#aiaas-chk-total");
      var citySelect = win.querySelector("#aiaas-chk-city");
      var countBadge = win.querySelector("#aiaas-chk-cart-count");
      var submitBtn = win.querySelector("#aiaas-btn-submit-order");

      if (!itemsContainer) return;

      var count = getCartCount();
      var subtotal = getCartSubtotal();
      var isDhaka = citySelect ? (citySelect.value.toLowerCase().indexOf("dhaka") !== -1) : true;
      var deliveryFee = isDhaka ? 60 : 120;
      var grandTotal = subtotal > 0 ? (subtotal + deliveryFee) : 0;

      if (countBadge) countBadge.textContent = count;
      if (subtotalEl) subtotalEl.textContent = "৳" + subtotal.toLocaleString() + " BDT";
      if (deliveryFeeEl) deliveryFeeEl.textContent = subtotal > 0 ? ("৳" + deliveryFee.toLocaleString() + " BDT") : "৳0 BDT";
      if (totalEl) totalEl.textContent = "৳" + grandTotal.toLocaleString() + " BDT";

      if (cartItems.length === 0) {
        itemsContainer.innerHTML = `
          <div style="text-align:center;padding:20px 10px;color:#94A3B8;">
            <div style="font-size:32px;margin-bottom:6px;">🛒</div>
            <div style="font-weight:700;font-size:13px;color:#64748B;">Your cart is currently empty</div>
            <div style="font-size:11px;margin-top:4px;margin-bottom:12px;">Browse our featured products and add them to your cart.</div>
            <button id="aiaas-empty-browse-btn" style="background:${primaryColor};color:#ffffff;border:none;border-radius:10px;padding:8px 16px;font-size:12px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">
              🛍️ Browse Products
            </button>
          </div>
        `;
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.style.opacity = "0.5";
          submitBtn.textContent = "Cart is Empty";
        }
        var emptyBrowseBtn = itemsContainer.querySelector("#aiaas-empty-browse-btn");
        if (emptyBrowseBtn) {
          emptyBrowseBtn.addEventListener("click", function () {
            checkoutModal.classList.remove("open");
            loadAndRenderProducts();
          });
        }
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.style.opacity = "1";
        submitBtn.textContent = "Confirm Order ➔";
      }

      var html = "";
      cartItems.forEach(function (item, idx) {
        var imgHtml = item.image_url ? `<img src="${item.image_url}" class="aiaas-cart-item-img" alt=""/>` : `<div class="aiaas-cart-item-img" style="display:flex;align-items:center;justify-content:center;font-size:16px;">🛍️</div>`;
        var meta = [];
        if (item.selected_size) meta.push("Size: " + item.selected_size);
        if (item.selected_color) meta.push("Color: " + item.selected_color);

        html += `
          <div class="aiaas-cart-item-row">
            <div class="aiaas-cart-item-info">
              ${imgHtml}
              <div style="min-width:0;">
                <div class="aiaas-cart-item-title">${item.title}</div>
                <div class="aiaas-cart-item-meta">৳${item.selling_price.toLocaleString()} ${meta.length > 0 ? '· ' + meta.join(', ') : ''}</div>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:6px;">
              <div class="aiaas-qty-picker" style="transform:scale(0.85);transform-origin:right center;">
                <button class="aiaas-qty-btn aiaas-cart-minus" data-idx="${idx}">−</button>
                <span class="aiaas-qty-val">${item.quantity}</span>
                <button class="aiaas-qty-btn aiaas-cart-plus" data-idx="${idx}">+</button>
              </div>
              <button class="aiaas-cart-item-remove aiaas-cart-del" data-idx="${idx}" title="Remove item">✕</button>
            </div>
          </div>
        `;
      });

      itemsContainer.innerHTML = html;

      // Bind events for cart stepper in drawer
      itemsContainer.querySelectorAll(".aiaas-cart-minus").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var idx = parseInt(btn.getAttribute("data-idx"));
          updateCartQty(idx, -1);
        });
      });
      itemsContainer.querySelectorAll(".aiaas-cart-plus").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var idx = parseInt(btn.getAttribute("data-idx"));
          updateCartQty(idx, 1);
        });
      });
      itemsContainer.querySelectorAll(".aiaas-cart-del").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var idx = parseInt(btn.getAttribute("data-idx"));
          removeFromCart(idx);
        });
      });
    }

    if (chkCity) {
      chkCity.addEventListener("change", function () {
        renderCartDrawer();
      });
    }

    var footerBox = win.querySelector(".aiaas-footer");
    var inputEl = win.querySelector(".aiaas-input");
    var sendBtn = win.querySelector(".aiaas-send-btn");
    var closeBtn = win.querySelector(".aiaas-close-btn");
    var titleEl = win.querySelector(".aiaas-header-title");

    function updateAIStatusUI(paused) {
      isAiPaused = paused;
      if (paused) {
        statusTxt.textContent = "Human Support Mode";
        handoverBtn.innerHTML = "🤖 Switch to AI";
      } else {
        statusTxt.textContent = "AI Active";
        handoverBtn.innerHTML = "👤 Talk to Human";
      }
    }

    // Toggle Chat
    function toggleChat() {
      isOpen = !isOpen;
      if (isOpen) {
        win.classList.add("open");
        if (visitorName) {
          inputEl.focus();
        } else {
          nameInp.focus();
        }
      } else {
        win.classList.remove("open");
      }
    }

    launcher.addEventListener("click", toggleChat);
    closeBtn.addEventListener("click", toggleChat);

    // 1-Click Handover Switcher
    handoverBtn.addEventListener("click", async function () {
      try {
        var res = await fetch(`${apiUrl}/public/widget/toggle-handover`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            widget_key: widgetKey,
            visitor_session_id: visitorSessionId,
            content: isAiPaused ? "resume_ai" : "request_human"
          })
        });
        if (res.ok) {
          var data = await res.json();
          updateAIStatusUI(data.ai_paused);
        }
      } catch (err) {
        console.error("Handover error:", err);
      }
    });

    // Header Cart & Bottom Bar triggers
    if (btnHeaderCart) {
      btnHeaderCart.addEventListener("click", function () {
        openCheckout();
      });
    }
    if (btnBarCheckout) {
      btnBarCheckout.addEventListener("click", function () {
        openCheckout();
      });
    }

    // Start Chat from Pre-Chat Form
    startBtn.addEventListener("click", function () {
      var n = nameInp.value.trim();
      var c = contactInp.value.trim();
      if (!n) {
        nameInp.focus();
        return;
      }
      if (!c) {
        contactInp.focus();
        return;
      }

      visitorName = n;
      visitorContact = c;
      localStorage.setItem("aiaas_vis_name_" + widgetKey, n);
      localStorage.setItem("aiaas_vis_contact_" + widgetKey, c);

      prechatBox.style.display = "none";
      messagesBox.style.display = "flex";
      chipsBox.style.display = "flex";
      footerBox.style.display = "flex";
      inputEl.focus();

      if (isEcomEnabled) {
        loadCart();
      }
      renderAdaptiveChips(currentBusinessCategory, isEcomEnabled);
      initSession();
    });

    // In-Chat E-Commerce Product Carousel Renderer
    async function loadAndRenderProducts() {
      try {
        var res = await fetch(`${apiUrl}/public/widget/products?widget_key=${widgetKey}`);
        if (res.ok) {
          var prods = await res.json();
          if (prods && prods.length > 0) {
            appendProductCarousel(prods);
          } else {
            appendMessage("No products are currently active in our store catalog.", "ai", "AI Assistant");
          }
        }
      } catch (err) {
        console.error("Failed to load products:", err);
      }
    }

    // ----------------- GENERATIVE UI & MICRO-COMPONENT REGISTRY -----------------
    function createProductCardElement(p, isCompact) {
      var card = document.createElement("div");
      card.className = "aiaas-prod-card" + (isCompact ? " compact" : "");
      var imgHtml = (p.images && p.images[0])
        ? `<img src="${p.images[0]}" class="aiaas-prod-img" alt=""/>`
        : `<div class="aiaas-prod-img" style="display:flex;align-items:center;justify-content:center;font-size:20px;">🛍️</div>`;

      // Variant options (sizes)
      var sizes = [];
      if (p.specifications && p.specifications.sizes && Array.isArray(p.specifications.sizes)) {
        sizes = p.specifications.sizes;
      } else if (p.specifications && p.specifications.size) {
        sizes = Array.isArray(p.specifications.size) ? p.specifications.size : [p.specifications.size];
      }

      var variantsHtml = "";
      if (sizes.length > 0) {
        variantsHtml = `<div class="aiaas-prod-variants">
          <span style="font-size:10.5px;color:#64748B;">Size:</span>
          ${sizes.map(function (s, sIdx) {
          return `<button class="aiaas-variant-chip ${sIdx === 0 ? 'active' : ''}" data-size="${s}">${s}</button>`;
        }).join("")}
        </div>`;
      }

      var hasDiscount = p.unit_price > p.selling_price && p.selling_price > 0;
      var discountPercent = hasDiscount ? Math.round(((p.unit_price - p.selling_price) / p.unit_price) * 100) : 0;
      var priceHtml = `<div class="aiaas-prod-price">৳${(p.selling_price || p.unit_price).toLocaleString()} BDT</div>`;
      if (hasDiscount) {
        priceHtml = `
          <div style="display:flex;align-items:baseline;gap:6px;margin-top:2px;">
            <span class="aiaas-prod-price">৳${p.selling_price.toLocaleString()} BDT</span>
            <span style="font-size:11px;color:#94A3B8;text-decoration:line-through;">৳${p.unit_price.toLocaleString()}</span>
            <span style="font-size:9.5px;font-weight:700;color:#059669;background:#ECFDF5;padding:1px 5px;border-radius:4px;border:1px solid #A7F3D0;">-${discountPercent}%</span>
          </div>
        `;
      }

      var currentQty = Math.max(1, parseInt(p.initial_quantity) || 1);
      var selectedSize = sizes.length > 0 ? sizes[0] : null;

      card.innerHTML = `
        <div class="aiaas-prod-header">
          ${imgHtml}
          <div class="aiaas-prod-info">
            <div style="display:flex;align-items:center;gap:4px;margin-bottom:2px;">
              <span style="font-size:9px;font-weight:800;text-transform:uppercase;color:${primaryColor};background:rgba(79,70,229,0.08);padding:1px 6px;border-radius:4px;">${p.category || 'Product'}</span>
              ${p.sku ? `<span style="font-size:9px;font-family:monospace;color:#94A3B8;">${p.sku}</span>` : ''}
            </div>
            <div class="aiaas-prod-title">${p.title}</div>
            ${priceHtml}
          </div>
        </div>
        ${variantsHtml}
        <div class="aiaas-prod-bottom-row">
          <div class="aiaas-qty-picker">
            <button class="aiaas-qty-btn aiaas-btn-minus">−</button>
            <span class="aiaas-qty-val">${currentQty}</span>
            <button class="aiaas-qty-btn aiaas-btn-plus">+</button>
          </div>
          <div class="aiaas-btn-actions" style="display:flex;align-items:center;gap:6px;flex:1;">
            <button class="aiaas-btn-add-cart" style="flex:1;display:flex;align-items:center;justify-content:center;gap:4px;padding:7px 8px;font-size:11px;font-weight:700;background:#F1F5F9;border:1px solid #CBD5E1;border-radius:8px;cursor:pointer;color:#1E293B;">
              🛒 Add to Cart
            </button>
            <button class="aiaas-prod-buy-btn" style="flex:1;display:flex;align-items:center;justify-content:center;gap:4px;padding:7px 10px;font-size:11px;font-weight:700;background:#059669;color:#ffffff;border:none;border-radius:8px;cursor:pointer;">
              ⚡ Buy Now
            </button>
          </div>
        </div>
      `;

      // Size chips
      card.querySelectorAll(".aiaas-variant-chip").forEach(function (chip) {
        chip.addEventListener("click", function () {
          card.querySelectorAll(".aiaas-variant-chip").forEach(function (c) { c.classList.remove("active"); });
          chip.classList.add("active");
          selectedSize = chip.getAttribute("data-size");
        });
      });

      // Quantity Stepper
      var minusBtn = card.querySelector(".aiaas-btn-minus");
      var plusBtn = card.querySelector(".aiaas-btn-plus");
      var qtyVal = card.querySelector(".aiaas-qty-val");

      minusBtn.addEventListener("click", function () {
        if (currentQty > 1) {
          currentQty--;
          qtyVal.textContent = currentQty;
        }
      });
      plusBtn.addEventListener("click", function () {
        currentQty++;
        qtyVal.textContent = currentQty;
      });

      // Add to Cart button
      var addBtn = card.querySelector(".aiaas-btn-add-cart");
      if (addBtn) {
        addBtn.addEventListener("click", function () {
          addToCart(p, currentQty, selectedSize);
        });
      }

      // Buy Now button (1-click purchase)
      var buyBtn = card.querySelector(".aiaas-prod-buy-btn");
      if (buyBtn) {
        buyBtn.addEventListener("click", function () {
          addToCart(p, currentQty, selectedSize);
          openCheckout();
        });
      }

      return card;
    }

    function renderInteractiveProductCard(product) {
      if (!product) return null;
      var container = document.createElement("div");
      container.className = "aiaas-prod-container";
      container.style.marginTop = "8px";
      var card = createProductCardElement(product, false);
      container.appendChild(card);
      return container;
    }

    function renderInteractiveCarousel(productsList) {
      if (!productsList || !productsList.length) return null;
      var container = document.createElement("div");
      var isScrollable = productsList.length > 3;
      container.className = "aiaas-prod-container" + (isScrollable ? " scrollable" : "");
      container.style.marginTop = "8px";

      if (isScrollable) {
        var headerBar = document.createElement("div");
        headerBar.className = "aiaas-prod-scroll-header";
        headerBar.innerHTML = `
          <span>🛍️ <b>${productsList.length}</b> Products Available</span>
          <span style="font-size:10px;color:#64748B;font-weight:600;display:flex;align-items:center;gap:3px;">Scroll down for more ↕</span>
        `;
        container.appendChild(headerBar);
      }

      productsList.forEach(function (p) {
        var card = createProductCardElement(p, true);
        container.appendChild(card);
      });
      return container;
    }

    function renderOrderTrackingCard(o) {
      if (!o) return null;
      var card = document.createElement("div");
      card.className = "aiaas-track-card";

      var status = (o.order_status || "pending").toLowerCase();
      var statusLabels = {
        "pending": "🟡 Placed",
        "confirmed": "🔵 Confirmed",
        "shipped": "🚚 In Transit / Shipped",
        "delivered": "🟢 Delivered",
        "cancelled": "🔴 Cancelled"
      };
      var statusBadgeText = statusLabels[status] || "📦 " + status.toUpperCase();

      var stepIndex = 1;
      if (status === "confirmed") stepIndex = 2;
      else if (status === "shipped") stepIndex = 3;
      else if (status === "delivered") stepIndex = 4;

      var steps = [
        { label: "Placed", num: 1 },
        { label: "Confirmed", num: 2 },
        { label: "Shipped", num: 3 },
        { label: "Delivered", num: 4 }
      ];

      var stepperHtml = `
        <div class="aiaas-stepper-wrap">
          <div style="position:absolute;top:9px;left:10%;right:10%;height:2px;background:#E2E8F0;z-index:1;"></div>
          <div style="position:absolute;top:9px;left:10%;width:${((stepIndex - 1) / 3) * 80}%;height:2px;background:#059669;z-index:1;transition:width 0.3s;"></div>
          ${steps.map(function (s) {
        var isPassed = s.num <= stepIndex;
        var isCurrent = s.num === stepIndex;
        return `
              <div class="aiaas-stepper-step">
                <div class="aiaas-step-dot ${isPassed ? 'active' : ''} ${isCurrent ? 'current' : ''}">
                  ${isPassed ? '✓' : s.num}
                </div>
                <span class="aiaas-step-label ${isPassed ? 'active' : ''}">${s.label}</span>
              </div>
            `;
      }).join("")}
        </div>
      `;

      var itemsHtml = "";
      if (o.items && o.items.length) {
        itemsHtml = `
          <div style="background:#F8FAFC;padding:8px;border-radius:8px;font-size:11px;color:#334155;display:flex;flex-direction:column;gap:4px;">
            ${o.items.map(function (it) {
          var itemTotal = it.line_total || it.total || ((it.unit_price || it.price || 0) * (it.quantity || 1));
          var sizeText = it.selected_size || it.size ? " (" + (it.selected_size || it.size) + ")" : "";
          return `<div style="display:flex;justify-content:space-between;align-items:center;"><span>${it.quantity}x ${it.title}${sizeText}</span><b>৳${Number(itemTotal).toLocaleString()}</b></div>`;
        }).join("")}
          </div>
        `;
      }

      var payText = o.payment_method === "bkash" ? "📱 bKash (" + (o.payment_status || "Paid") + ")" : "💵 Cash on Delivery";

      card.innerHTML = `
        <div class="aiaas-track-header">
          <div>
            <span style="font-size:10px;font-family:monospace;font-weight:800;color:${primaryColor};background:rgba(79,70,229,0.08);padding:2px 6px;border-radius:4px;">${o.order_number}</span>
            <div style="font-size:10px;color:#94A3B8;margin-top:2px;">${o.customer_name} • ${o.delivery_city}</div>
          </div>
          <span class="aiaas-track-badge ${status}">${statusBadgeText}</span>
        </div>
        ${stepperHtml}
        ${itemsHtml}
        <div style="display:flex;align-items:center;justify-content:space-between;font-size:11.5px;padding-top:4px;border-top:1px dashed #E2E8F0;">
          <span style="color:#64748B;">Total Amount:</span>
          <span style="font-weight:800;color:#059669;">৳${(o.total_amount || 0).toLocaleString()} BDT <span style="font-size:10px;color:#64748B;font-weight:500;">(${payText})</span></span>
        </div>
        <div style="font-size:10.5px;color:#475569;background:#F1F5F9;padding:6px 8px;border-radius:6px;">
          📍 <b>Address:</b> ${o.delivery_address}<br/>
          ℹ️ <b>Status Note:</b> ${o.tracking_notes || "Scheduled for courier dispatch."}
        </div>
      `;

      return card;
    }

    // Micro-Component Registry for 100+ Future Generative UI Modules
    var UI_COMPONENTS = {
      "product_card": function (data) {
        return renderInteractiveProductCard(data.product);
      },
      "product_carousel": function (data) {
        return renderInteractiveCarousel(data.products);
      },
      "order_tracking_card": function (data) {
        return renderOrderTrackingCard(data.order);
      }
    };

    function appendProductCarousel(productsList) {
      var wrapper = document.createElement("div");
      wrapper.className = "aiaas-msg ai";

      var authorDiv = document.createElement("div");
      authorDiv.className = "aiaas-msg-author";
      authorDiv.textContent = "🛍️ Featured Store Products";
      wrapper.appendChild(authorDiv);

      var comp = renderInteractiveCarousel(productsList);
      if (comp) {
        wrapper.appendChild(comp);
      }

      messagesBox.appendChild(wrapper);
      messagesBox.scrollTop = messagesBox.scrollHeight;
    }

    function openCheckout() {
      chkName.value = visitorName || chkName.value || "";
      chkPhone.value = visitorContact || chkPhone.value || "";
      renderCartDrawer();
      checkoutModal.classList.add("open");
    }

    if (btnCloseCheckout) {
      btnCloseCheckout.addEventListener("click", function () {
        checkoutModal.classList.remove("open");
      });
    }

    if (btnSubmitOrder) {
      btnSubmitOrder.addEventListener("click", async function () {
        if (cartItems.length === 0) {
          alert("Your shopping cart is empty!");
          return;
        }

        var name = chkName.value.trim();
        var phone = chkPhone.value.trim();
        var address = chkAddress.value.trim();
        var city = chkCity.value;
        var paymentMethod = chkPayment.value;

        if (!name) { chkName.focus(); return; }
        if (!phone) { chkPhone.focus(); return; }
        if (!address) { chkAddress.focus(); return; }

        btnSubmitOrder.disabled = true;
        btnSubmitOrder.textContent = "Processing Order...";

        var itemsPayload = cartItems.map(function (item) {
          return {
            product_id: item.id,
            title: item.title,
            price: item.selling_price,
            quantity: item.quantity,
            selected_size: item.selected_size,
            selected_color: item.selected_color,
            image_url: item.image_url
          };
        });

        try {
          if (paymentMethod === "bkash") {
            var res = await fetch(`${apiUrl}/public/widget/orders/bkash/init`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                widget_key: widgetKey,
                visitor_session_id: visitorSessionId,
                customer_name: name,
                customer_phone: phone,
                delivery_address: address,
                delivery_city: city,
                payment_method: "bkash",
                items: itemsPayload
              })
            });

            if (res.ok) {
              var bkData = await res.json();
              checkoutModal.classList.remove("open");
              clearCart();

              if (!visitorName && name) {
                visitorName = name;
                visitorContact = phone;
                localStorage.setItem("aiaas_vis_name_" + widgetKey, name);
                localStorage.setItem("aiaas_vis_contact_" + widgetKey, phone);
                if (prechatBox) prechatBox.style.display = "none";
                if (messagesBox) messagesBox.style.display = "flex";
                if (chipsBox) chipsBox.style.display = "flex";
                if (footerBox) footerBox.style.display = "flex";
              }

              // Append Interactive bKash Pending Card with Retry & Switch-to-COD Buttons
              appendBkashPendingCard(bkData);

              if (bkData.bkashURL) {
                window.open(bkData.bkashURL, "bKashPayment", "width=460,height=660");
              }
            } else {
              var err = await res.json().catch(() => ({}));
              alert(err.detail || "bKash payment initialization failed. Please try Cash on Delivery.");
            }
          } else {
            var res = await fetch(`${apiUrl}/public/widget/orders/checkout`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                widget_key: widgetKey,
                visitor_session_id: visitorSessionId,
                customer_name: name,
                customer_phone: phone,
                delivery_address: address,
                delivery_city: city,
                payment_method: "cash_on_delivery",
                items: itemsPayload
              })
            });

            if (res.ok) {
              var orderData = await res.json();
              checkoutModal.classList.remove("open");
              clearCart();

              // If visitor info was not set yet, update it
              if (!visitorName && name) {
                visitorName = name;
                visitorContact = phone;
                localStorage.setItem("aiaas_vis_name_" + widgetKey, name);
                localStorage.setItem("aiaas_vis_contact_" + widgetKey, phone);
                if (prechatBox) prechatBox.style.display = "none";
                if (messagesBox) messagesBox.style.display = "flex";
                if (chipsBox) chipsBox.style.display = "flex";
                if (footerBox) footerBox.style.display = "flex";
              }

              var itemsSummary = orderData.items_json.map(function (it) {
                return `  • **${it.title}** (x${it.quantity}) - ৳${(it.unit_price * it.quantity).toLocaleString()} BDT`;
              }).join("\n");

              appendMessage(`🎉 **Order Placed Successfully!**\n\n- **Order #:** \`${orderData.order_number}\`\n- **Items Ordered (${orderData.items_json.length}):**\n${itemsSummary}\n- **Delivery Charge:** ৳${orderData.delivery_charge.toLocaleString()} BDT\n- **Total Amount:** **৳${orderData.total_amount.toLocaleString()} BDT**\n- **Delivery Address:** ${orderData.delivery_address}, ${orderData.delivery_city}\n- **Payment Method:** 💵 Cash on Delivery (COD)\n- **SMS Notification:** Dispatched to \`${orderData.customer_phone}\``, "system", "Order Desk");
            } else {
              var err = await res.json().catch(() => ({}));
              alert(err.detail || "Could not place order. Please try again.");
            }
          }
        } catch (e) {
          alert("Checkout network error. Please try again.");
        } finally {
          btnSubmitOrder.disabled = false;
          btnSubmitOrder.textContent = "Confirm Order ➔";
        }
      });
    }

    // Load persisted cart on init if ecommerce is active
    if (isEcomEnabled) {
      loadCart();
    }

    // Render Interactive bKash Pending Action Card with 5-Minute Auto-Expiry Timer
    function appendBkashPendingCard(bkData) {
      var ordNum = bkData.order_number || bkData.merchantInvoiceNumber;
      var totalAmt = bkData.total_amount ? Number(bkData.total_amount).toLocaleString() : "0";
      var currentBkashUrl = bkData.bkashURL || "";

      // Remove previous pending card if any
      var prevCard = win.querySelector("#aiaas-pay-card-" + ordNum);
      if (prevCard) {
        if (prevCard._timerInterval) clearInterval(prevCard._timerInterval);
        prevCard.remove();
      }

      var cardDiv = document.createElement("div");
      cardDiv.className = "aiaas-msg system";
      cardDiv.id = "aiaas-pay-card-" + ordNum;

      cardDiv.innerHTML = `
        <div class="aiaas-msg-author">📱 bKash Payment Desk</div>
        <div class="aiaas-msg-body">
          <div class="aiaas-pay-action-card">
            <div class="aiaas-pay-action-title">
              <span id="aiaas-pay-title-${ordNum}">📱 bKash Payment Pending</span>
              <span style="margin-left:auto; font-size:11px; background:#FCE7F3; color:#BE185D; padding:2px 8px; border-radius:12px;">৳${totalAmt} BDT</span>
            </div>
            <div class="aiaas-pay-action-desc" id="aiaas-pay-desc-${ordNum}">
              Order #<strong>${ordNum}</strong> initiated. If your bKash payment window closed or timed out, click below to re-open or switch to Cash on Delivery:
            </div>
            <div class="aiaas-pay-btn-group" id="aiaas-btn-grp-${ordNum}">
              <button class="aiaas-btn-reopen-bkash" id="btn-reopen-${ordNum}">
                ⚡ Re-open bKash Checkout
              </button>
              <button class="aiaas-btn-switch-cod" id="btn-switch-cod-${ordNum}">
                💵 Switch to Cash on Delivery
              </button>
            </div>
            <div class="aiaas-pay-timer" style="font-size:11px;color:#9D174D;margin-top:8px;padding-top:6px;border-top:1px dashed #FBCFE8;display:flex;align-items:center;justify-content:space-between;">
              <span>⏳ bKash session expires in:</span>
              <strong id="aiaas-timer-${ordNum}" style="font-family:monospace;font-size:12px;background:#FCE7F3;padding:1px 6px;border-radius:6px;color:#BE185D;">05:00</strong>
            </div>
          </div>
        </div>
      `;

      messagesBox.appendChild(cardDiv);
      messagesBox.scrollTop = messagesBox.scrollHeight;

      // 5-Minute Auto-Expiry Timer Countdown
      var timeLeftSeconds = 300; // 5 minutes
      var timerEl = cardDiv.querySelector("#aiaas-timer-" + ordNum);
      var titleEl = cardDiv.querySelector("#aiaas-pay-title-" + ordNum);
      var descEl = cardDiv.querySelector("#aiaas-pay-desc-" + ordNum);
      var btnReopen = cardDiv.querySelector("#btn-reopen-" + ordNum);
      var btnSwitch = cardDiv.querySelector("#btn-switch-cod-" + ordNum);

      var timerInterval = setInterval(function () {
        timeLeftSeconds--;
        if (timeLeftSeconds <= 0) {
          clearInterval(timerInterval);
          if (timerEl) {
            timerEl.textContent = "EXPIRED";
            timerEl.style.background = "#FEE2E2";
            timerEl.style.color = "#DC2626";
          }
          if (titleEl) {
            titleEl.innerHTML = "⚠️ bKash Session Expired";
          }
          if (descEl) {
            descEl.innerHTML = `bKash payment session for order #<strong>${ordNum}</strong> has expired. Click below to convert your order to <strong>Cash on Delivery (COD)</strong>:`;
          }
          if (btnReopen) {
            btnReopen.style.display = "none";
          }
          if (btnSwitch) {
            btnSwitch.style.background = "#059669";
            btnSwitch.style.color = "#ffffff";
            btnSwitch.style.border = "none";
            btnSwitch.innerHTML = "🚀 Confirm as Cash on Delivery ➔";
          }
        } else {
          var mins = Math.floor(timeLeftSeconds / 60);
          var secs = timeLeftSeconds % 60;
          if (timerEl) {
            timerEl.textContent = (mins < 10 ? "0" : "") + mins + ":" + (secs < 10 ? "0" : "") + secs;
          }
        }
      }, 1000);

      cardDiv._timerInterval = timerInterval;

      // Event: Re-open bKash Checkout
      if (btnReopen) {
        btnReopen.addEventListener("click", async function () {
          btnReopen.disabled = true;
          btnReopen.textContent = "Opening bKash Gateway...";
          try {
            var res = await fetch(`${apiUrl}/public/widget/orders/bkash/retry`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                widget_key: widgetKey,
                visitor_session_id: visitorSessionId,
                order_number: ordNum
              })
            });
            var data = await res.json();
            if (data.status === "already_paid") {
              // Order was already paid! Remove retry card
              if (cardDiv._timerInterval) clearInterval(cardDiv._timerInterval);
              cardDiv.remove();
              appendMessage(`🎉 **Order #${ordNum} is already verified and PAID!**`, "system", "bKash Verified");
            } else if (data.bkashURL) {
              // Reset timer on re-attempt
              timeLeftSeconds = 300;
              window.open(data.bkashURL, "bKashPayment", "width=460,height=660");
            } else {
              window.open(currentBkashUrl, "bKashPayment", "width=460,height=660");
            }
          } catch (e) {
            window.open(currentBkashUrl, "bKashPayment", "width=460,height=660");
          } finally {
            btnReopen.disabled = false;
            btnReopen.textContent = "⚡ Re-open bKash Checkout";
          }
        });
      }

      // Event: Switch to Cash on Delivery
      if (btnSwitch) {
        btnSwitch.addEventListener("click", async function () {
          btnSwitch.disabled = true;
          btnSwitch.textContent = "Switching to COD...";
          try {
            var res = await fetch(`${apiUrl}/public/widget/orders/switch-cod`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                widget_key: widgetKey,
                visitor_session_id: visitorSessionId,
                order_number: ordNum
              })
            });
            if (res.ok) {
              var data = await res.json();
              if (cardDiv._timerInterval) clearInterval(cardDiv._timerInterval);
              cardDiv.remove();
              appendMessage(
                `🎉 **Payment Method Switched to Cash on Delivery!**\n\n` +
                `• **Order Number:** \`${ordNum}\`\n` +
                `• **Total Amount:** ৳${totalAmt} BDT\n` +
                `• **Status:** Confirmed (Pay upon delivery)\n` +
                `• **SMS:** Confirmation sent to your mobile phone.`,
                "system",
                "Order Desk"
              );
            } else {
              var err = await res.json().catch(() => ({}));
              alert(err.detail || "Could not switch payment method.");
            }
          } catch (e) {
            alert("Network error switching payment method.");
          } finally {
            btnSwitch.disabled = false;
            btnSwitch.textContent = "💵 Switch to Cash on Delivery";
          }
        });
      }
    }

    function formatMessageTime(timestamp) {
      try {
        var d = timestamp ? new Date(timestamp) : new Date();
        var now = new Date();
        var time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        if (d.toDateString() === now.toDateString()) {
          return time;
        }
        var month = d.toLocaleDateString([], { month: 'short', day: 'numeric' });
        return month + ", " + time;
      } catch (e) {
        return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
    }

    // Message Appender with Open-Source marked.js Markdown, WhatsApp Date/Time, Generative UI Components & Anti-Duplication
    function appendMessage(text, sender, author, timestamp, uiComponent) {
      if (!text && !uiComponent) return;
      var trimmed = (text || "").trim();
      var now = Date.now();
      var compKey = uiComponent ? JSON.stringify(uiComponent) : "";
      var dedupeKey = sender + ":::" + trimmed + ":::" + compKey;

      for (var i = recentMessages.length - 1; i >= 0; i--) {
        if (recentMessages[i].key === dedupeKey && (now - recentMessages[i].time < 10000)) {
          return;
        }
      }
      recentMessages.push({ key: dedupeKey, time: now });
      if (recentMessages.length > 50) recentMessages.shift();

      var msg = document.createElement("div");
      msg.className = "aiaas-msg " + sender;

      var renderedHtml = trimmed ? renderMarkdown(trimmed) : "";
      var timeStr = formatMessageTime(timestamp);
      var checkHtml = sender === "visitor" ? '<span class="aiaas-msg-check">✓✓</span>' : '';
      var metaHtml = `<div class="aiaas-msg-meta"><span class="aiaas-msg-time">${timeStr}</span>${checkHtml}</div>`;
      var bodyHtml = renderedHtml ? `<div class="aiaas-msg-body" data-raw="${encodeURIComponent(trimmed)}">${renderedHtml}</div>` : "";

      if (author && sender !== "visitor") {
        msg.innerHTML = `<div class="aiaas-msg-author">${author}</div>${bodyHtml}${metaHtml}`;
      } else {
        msg.innerHTML = `${bodyHtml}${metaHtml}`;
      }

      // Render Generative UI Component if attached
      if (uiComponent && uiComponent.type && UI_COMPONENTS[uiComponent.type]) {
        try {
          var compEl = UI_COMPONENTS[uiComponent.type](uiComponent.data);
          if (compEl) {
            var metaEl = msg.querySelector(".aiaas-msg-meta");
            if (metaEl) {
              msg.insertBefore(compEl, metaEl);
            } else {
              msg.appendChild(compEl);
            }
          }
        } catch (e) {
          console.error("Generative UI component render error:", e);
        }
      }

      messagesBox.appendChild(msg);
      messagesBox.scrollTop = messagesBox.scrollHeight;
    }

    function showTyping() {
      if (isTyping) return;
      isTyping = true;
      var typing = document.createElement("div");
      typing.className = "aiaas-typing";
      typing.id = "aiaas-typing-indicator";
      typing.innerHTML = `<div class="aiaas-dot"></div><div class="aiaas-dot"></div><div class="aiaas-dot"></div>`;
      messagesBox.appendChild(typing);
      messagesBox.scrollTop = messagesBox.scrollHeight;
    }

    function hideTyping() {
      isTyping = false;
      var typing = messagesBox.querySelector("#aiaas-typing-indicator");
      if (typing) typing.remove();
    }

    // Connect WebSocket
    function connectWs(convId) {
      if (!convId) return;
      try {
        var wsUrl = apiUrl.replace("http://", "ws://").replace("https://", "wss://");
        socket = new WebSocket(`${wsUrl}/ws/chat/${convId}`);

        socket.onopen = function () {
          isWsConnected = true;
        };

        socket.onclose = function () {
          isWsConnected = false;
        };

        socket.onmessage = function (e) {
          try {
            var data = JSON.parse(e.data);
            if (data.event === "ai_state_changed") {
              updateAIStatusUI(data.ai_paused);
              if (data.content) {
                appendMessage(data.content, "system", null, data.created_at);
              }
            } else if (data.event === "message" && data.sender_type !== "visitor") {
              hideTyping();
              appendMessage(data.content, data.sender_type, data.sender_name || (data.sender_type === "ai" ? "Gemini AI" : "Support Agent"), data.created_at, data.ui_component);
            }
          } catch (err) {
            console.error(err);
          }
        };
      } catch (e) {
        console.error("WebSocket connection error:", e);
      }
    }

    // Initialize Session with Backend (sending visitor details)
    async function initSession() {
      try {
        var isEmail = visitorContact && visitorContact.indexOf("@") > -1;
        var res = await fetch(`${apiUrl}/public/widget/init`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            widget_key: widgetKey,
            visitor_session_id: visitorSessionId,
            visitor_name: visitorName || undefined,
            visitor_email: isEmail ? visitorContact : undefined,
            visitor_phone: !isEmail ? (visitorContact || undefined) : undefined,
            current_url: window.location.href,
            user_agent: navigator.userAgent
          })
        });

        if (!res.ok) throw new Error("Failed to init widget session");
        var data = await res.json();
        conversationId = data.conversation_id;

        if (data.widget) {
          isEcomEnabled = Boolean(data.widget.ecommerce && data.widget.ecommerce.enabled);
          currentBusinessCategory = (data.widget.business_category || (isEcomEnabled ? "ecommerce" : "erp")).toLowerCase();

          // Adaptive Header Cart Button display
          if (btnHeaderCart) {
            btnHeaderCart.style.display = isEcomEnabled ? "inline-flex" : "none";
          }
          if (!isEcomEnabled && cartBar) {
            cartBar.style.display = "none";
          }

          // Adaptive Quick Action Chips
          renderAdaptiveChips(currentBusinessCategory, isEcomEnabled);

          // Visitor Cart Initializer
          if (isEcomEnabled) {
            loadCart();
          }

          var titleText = data.widget.header_title || data.widget.name || "Live Support";
          titleEl.textContent = titleText;
          var prechatTitle = win.querySelector(".aiaas-prechat-title");
          if (prechatTitle) {
            prechatTitle.textContent = "Welcome to " + titleText + "!";
          }

          if (data.widget.primary_color) {
            launcher.style.background = data.widget.primary_color;
            win.querySelector(".aiaas-header").style.background = data.widget.primary_color;
            sendBtn.style.background = data.widget.primary_color;
            startBtn.style.background = data.widget.primary_color;
            var badgeEl = win.querySelector(".aiaas-prechat-badge");
            if (badgeEl) badgeEl.style.color = data.widget.primary_color;
          }
        }

        // Render previous messages or personalized welcome message
        if (data.messages && data.messages.length > 0) {
          messagesBox.innerHTML = "";
          data.messages.forEach(function (m) {
            appendMessage(m.content, m.sender_type, m.sender_name, m.created_at, m.ui_component);
          });
        } else {
          var welcomeMsg = visitorName
            ? "Hello **" + visitorName + "**! Welcome to " + (data.widget && data.widget.header_title ? data.widget.header_title : "our live support") + ". How can we assist your business today?"
            : (data.widget && data.widget.welcome_message ? data.widget.welcome_message : "Welcome! How can we assist you today?");
          appendMessage(welcomeMsg, "ai", "AI Assistant", new Date().toISOString());
        }

        connectWs(conversationId);
      } catch (err) {
        console.error("Enterprise widget init error:", err);
      }
    }

    // Send Message
    async function sendMessage() {
      var text = inputEl.value.trim();
      if (!text) return;
      inputEl.value = "";

      appendMessage(text, "visitor");
      showTyping();

      try {
        var res = await fetch(`${apiUrl}/public/widget/message`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            widget_key: widgetKey,
            visitor_session_id: visitorSessionId,
            content: text
          })
        });

        var data = await res.json();
        hideTyping();

        if (data.is_handover_requested) {
          updateAIStatusUI(true);
        } else if (data.ai_response) {
          appendMessage(data.ai_response, "ai", "AI Assistant", null, data.ui_component);
        }
      } catch (err) {
        hideTyping();
        console.error("Send message error:", err);
        appendMessage("Sorry, we could not deliver your message right now. Please try again.", "system");
      }
    }

    sendBtn.addEventListener("click", sendMessage);
    inputEl.addEventListener("keypress", function (e) {
      if (e.key === "Enter") {
        sendMessage();
      }
    });

    // Listen for Real-Time bKash Popup PostMessage Events
    window.addEventListener("message", function (event) {
      if (!event || !event.data) return;

      if (event.data.type === "AIAAS_BKASH_PAYMENT_SUCCESS") {
        var ordNum = event.data.order_number || "ORD-CONFIRMED";
        var trx = event.data.trx_id || "TRX-VERIFIED";
        var amt = event.data.amount || "";

        // Remove Pending bKash Card if present in DOM
        var pendingCard = win.querySelector("#aiaas-pay-card-" + ordNum);
        if (pendingCard) {
          if (pendingCard._timerInterval) clearInterval(pendingCard._timerInterval);
          pendingCard.remove();
        }

        appendMessage(
          `### 🧾 bKash Payment Verified & Confirmed\n\n` +
          `**Status:** 🟢 **PAID & VERIFIED** (bKash Online Gateway)\n\n` +
          `| Invoice Detail | Value |\n` +
          `| :--- | :--- |\n` +
          `| **Order Number** | \`${ordNum}\` |\n` +
          `| **bKash TrxID** | \`${trx}\` |\n` +
          `| **Total Amount Paid** | **৳${Number(amt).toLocaleString()} BDT** |\n` +
          `| **Payment Status** | ✅ Confirmed & Settled |\n\n` +
          `> 📱 **SMS Confirmation:** Dispatched to customer mobile.\n` +
          `> 🚚 **Next Step:** Our dispatch team is currently packing your parcel!`,
          "system",
          "bKash Verified"
        );
      } else if (event.data.type === "AIAAS_BKASH_PAYMENT_FAILED_OR_CANCELLED") {
        var ordNum = event.data.order_number;
        if (ordNum) {
          var pendingCard = win.querySelector("#aiaas-pay-card-" + ordNum);
          if (pendingCard) {
            var titleEl = pendingCard.querySelector("#aiaas-pay-title-" + ordNum);
            var descEl = pendingCard.querySelector("#aiaas-pay-desc-" + ordNum);
            var btnSwitch = pendingCard.querySelector("#btn-switch-cod-" + ordNum);

            if (titleEl) titleEl.innerHTML = "⚠️ bKash Payment Cancelled";
            if (descEl) descEl.innerHTML = `bKash payment for order #<strong>${ordNum}</strong> was cancelled or closed. You can re-open checkout or switch to <strong>Cash on Delivery (COD)</strong>:`;
            if (btnSwitch) {
              btnSwitch.style.background = "#059669";
              btnSwitch.style.color = "#ffffff";
              btnSwitch.style.border = "none";
              btnSwitch.innerHTML = "💵 Switch to Cash on Delivery ➔";
            }
          }
        }
      }
    });

    // Boot session immediately on load to dynamically fetch store header title, branding, colors & chat history
    initSession();

    // Load official marked library
    loadMarkedLibrary(apiUrl, function () {
      if (messagesBox) {
        var aiBodies = messagesBox.querySelectorAll(".aiaas-msg.ai .aiaas-msg-body");
        aiBodies.forEach(function (el) {
          if (el.dataset.raw) {
            el.innerHTML = renderMarkdown(decodeURIComponent(el.dataset.raw));
          }
        });
      }
    });
  }

  window.EnterpriseChatWidget = {
    init: function (config) {
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
          createWidget(config);
        });
      } else {
        createWidget(config);
      }
    }
  };

  // Auto-init if script tag has data-widget-key
  try {
    var autoScript = document.currentScript || document.querySelector("script[data-widget-key]");
    if (autoScript && autoScript.getAttribute("data-widget-key")) {
      var autoKey = autoScript.getAttribute("data-widget-key");
      var autoApi = autoScript.getAttribute("data-api-url") || (window.location.origin.includes("3000") ? "http://127.0.0.1:8000/api/v1" : window.location.origin + "/api/v1");
      var autoColor = autoScript.getAttribute("data-primary-color") || "#4F46E5";
      var autoPos = autoScript.getAttribute("data-position") || "bottom-right";

      window.EnterpriseChatWidget.init({
        widgetKey: autoKey,
        apiUrl: autoApi,
        primaryColor: autoColor,
        position: autoPos
      });
    }
  } catch (e) {
    console.error("Widget auto-init notice:", e);
  }
})(window, document);
