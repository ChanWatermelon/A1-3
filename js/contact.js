/* ===========================================================================
   contact.js — 문의하기 폼

   AI 기능과 동일한 원칙으로 동작한다.
     · 빈 입력 / 형식 오류는 서버에 보내기 전에 막는다.
     · 15초 안에 응답이 없으면 요청을 중단하고 안내한다.
     · 서버 오류(4xx/5xx)는 코드에 맞는 한국어 메시지로 바꿔 보여 준다.
   =========================================================================== */

(function () {
  'use strict';

  const { $, toast } = window.Molip;

  const form = $('#contactForm');
  if (!form) return;

  const nameInput = $('#name');
  const emailInput = $('#email');
  const topicInput = $('#topic');
  const messageInput = $('#message');
  const messageLen = $('#messageLen');
  const submitBtn = $('#contactBtn');
  const status = $('#contactStatus');

  const TIMEOUT_MS = 15000;
  const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  /* ---- 글자 수 표시 -------------------------------------------------------- */
  messageInput.addEventListener('input', () => {
    messageLen.textContent = String(messageInput.value.length);
    messageInput.classList.remove('is-invalid');
  });
  nameInput.addEventListener('input', () => nameInput.classList.remove('is-invalid'));
  emailInput.addEventListener('input', () => emailInput.classList.remove('is-invalid'));

  /* ---- 상태 메시지 --------------------------------------------------------- */
  function setStatus(kind, text) {
    status.className = 'form-status' + (kind ? ' is-' + kind : '');
    status.textContent = text || '';
  }

  function fail(field, text) {
    if (field) {
      field.classList.add('is-invalid');
      field.focus();
    }
    setStatus('error', text);
  }

  const ERROR_TEXT = {
    EMPTY_INPUT:   '이름과 문의 내용을 모두 입력해 주세요.',
    TOO_SHORT:     '문의 내용을 10자 이상 적어 주세요.',
    TOO_LONG:      '문의 내용이 너무 깁니다. 500자 이내로 줄여 주세요.',
    INVALID_EMAIL: '이메일 형식이 올바르지 않습니다.',
    RATE_LIMITED:  '요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.',
    UPSTREAM_ERROR:'접수 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.',
    TIMEOUT:       '응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.',
    NETWORK:       '네트워크에 연결할 수 없습니다. 연결 상태를 확인해 주세요.',
    UNKNOWN:       '알 수 없는 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'
  };

  /* ---- 제출 --------------------------------------------------------------- */
  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const name = nameInput.value.trim();
    const email = emailInput.value.trim();
    const message = messageInput.value.trim();

    // (1) 필수값 확인
    if (!name) return fail(nameInput, '이름 또는 닉네임을 입력해 주세요.');
    if (!message) return fail(messageInput, '문의 내용을 입력해 주세요.');
    if (message.length < 10) return fail(messageInput, ERROR_TEXT.TOO_SHORT);
    // (2) 선택 입력이지만 값이 있으면 형식을 확인한다.
    if (email && !EMAIL_PATTERN.test(email)) return fail(emailInput, ERROR_TEXT.INVALID_EMAIL);

    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, TIMEOUT_MS);

    submitBtn.disabled = true;
    submitBtn.classList.add('is-loading');
    submitBtn.querySelector('.btn-label').textContent = '보내는 중…';
    setStatus('', '');

    try {
      const response = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, topic: topicInput.value, message }),
        signal: controller.signal
      });

      let body = null;
      try {
        body = await response.json();
      } catch (e) {
        body = null;
      }

      if (!response.ok || !body || body.ok !== true) {
        const code = (body && body.error && body.error.code) ||
          (response.status === 429 ? 'RATE_LIMITED' : response.status >= 500 ? 'UPSTREAM_ERROR' : 'UNKNOWN');
        setStatus('error', ERROR_TEXT[code] || ERROR_TEXT.UNKNOWN);
        return;
      }

      setStatus('ok', body.message || '문의가 정상적으로 접수되었습니다. 감사합니다!');
      toast('문의를 접수했습니다');
      form.reset();
      messageLen.textContent = '0';
    } catch (error) {
      setStatus('error', timedOut ? ERROR_TEXT.TIMEOUT : ERROR_TEXT.NETWORK);
    } finally {
      clearTimeout(timer);
      submitBtn.disabled = false;
      submitBtn.classList.remove('is-loading');
      submitBtn.querySelector('.btn-label').textContent = '문의 보내기';
    }
  });
})();
