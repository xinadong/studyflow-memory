<template>
  <div class="agent-identity">
    <span class="agent-mark" aria-hidden="true">
      <svg width="29" height="29" viewBox="0 0 32 32" fill="none">
        <path d="M16 5C17.6 11.4 20.6 14.4 27 16C20.6 17.6 17.6 20.6 16 27C14.4 20.6 11.4 17.6 5 16C11.4 14.4 14.4 11.4 16 5Z" fill="currentColor"/>
        <circle cx="25.5" cy="6.5" r="2" fill="currentColor" opacity=".55"/>
      </svg>
    </span>
    <div class="agent-name"><strong>Flow Agent</strong><span>你的学习助手</span></div>
    <span class="agent-detail" aria-hidden="true"><i/><i/><i/></span>
  </div>
</template>

<style scoped>
.agent-identity{display:flex;align-items:center;gap:12px;min-width:0}
.agent-mark{position:relative;display:grid;place-items:center;flex:0 0 46px;height:46px;border:1px solid #fff;border-radius:16px;background:linear-gradient(140deg,#e5f7fc,#e9e8ff 80%);color:#7c7cdb;box-shadow:0 4px 12px #7f8bd016,inset 0 1px 1px #fff}
.agent-name{display:grid;gap:5px;min-width:0}
.agent-name strong{color:#35416b;font-size:15px;font-weight:700;letter-spacing:-.2px;line-height:1.2}
.agent-name span{color:#939cb7;font-size:10px;line-height:1.4;letter-spacing:.04em}
.agent-detail{display:flex;align-items:center;gap:3px;margin-left:auto;padding-left:4px}
.agent-detail i{display:block;width:3px;height:3px;border-radius:50%;background:#c6cce4}
.agent-detail i:nth-child(2){height:10px;border-radius:3px;background:#b6bfe0}
.agent-detail i:last-child{height:6px;border-radius:3px}
</style>
