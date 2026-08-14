/* ===========================================================================
   routine.js — AI 몰입 설계 기능

   흐름
     [입력] 폼 값 읽기 → 클라이언트 유효성 검사(빈 입력 차단)
        ↓
     [요청] fetch('/api/routine', {method:'POST', body:JSON})
            · AbortController 로 25초 타임아웃 처리
        ↓
     [응답] 성공 → 타임라인 렌더링 + 로컬 기록 저장
            실패 → 오류 코드별 안내 메시지 표시

   서버 응답 형식
     성공 : { ok: true,  data: { headline, strategy, blocks[], checklist[], caution, provider, model } }
     실패 : { ok: false, error: { code, message } }
   =========================================================================== */

(function () {
  'use strict';

  const { $, $$, toast } = window.Molip;

  /* ---- DOM ---------------------------------------------------------------- */
  const form = $('#routineForm');
  if (!form) return;

  const tasksInput = $('#tasks');
  const tasksLen = $('#tasksLen');
  const minutesInput = $('#minutes');
  const startTimeInput = $('#startTime');
  const energyInput = $('#energy');
  const energyOut = $('#energyOut');
  const blockerInput = $('#blocker');
  const submitBtn = $('#submitBtn');
  const resetBtn = $('#resetBtn');

  const stateIdle = $('#resultIdle');
  const stateLoading = $('#resultLoading');
  const stateError = $('#resultError');
  const stateSuccess = $('#resultSuccess');
  const loadingHint = $('#loadingHint');

  const errorTitle = $('#errorTitle');
  const errorMessage = $('#errorMessage');
  const errorHint = $('#errorHint');
  const retryBtn = $('#retryBtn');

  const resultMeta = $('#resultMeta');
  const resultHeadline = $('#resultHeadline');
  const resultStrategy = $('#resultStrategy');
  const timeline = $('#timeline');
  const resultChecklist = $('#resultChecklist');
  const resultCaution = $('#resultCaution');
  const copyBtn = $('#copyBtn');

  const historyWrap = $('#historyWrap');
  const historyList = $('#historyList');
  const clearHistoryBtn = $('#clearHistoryBtn');

  /* ---- 설정 --------------------------------------------------------------- */
  const API_URL = '/api/routine';
  const TIMEOUT_MS = 25000;          // 이 시간을 넘기면 요청을 중단한다.
  const SLOW_HINT_MS = 8000;         // 이 시간이 지나면 "조금 더 걸린다" 안내로 바꾼다.
  const HISTORY_KEY = 'molip-history';
  const HISTORY_MAX = 3;

  let inFlight = null;               // 진행 중인 AbortController
  let lastPayload = null;            // '다시 시도' 버튼용 마지막 요청 값

  /* -------------------------------------------------------------------------
     입력 보조 (글자 수 / 컨디션 표시 / 시작 시각 기본값)
     ------------------------------------------------------------------------- */
  function updateCounter() {
    const length = tasksInput.value.length;
    tasksLen.textContent = String(length);
    tasksLen.parentElement.classList.toggle('is-near', length > 260);
  }
  tasksInput.addEventListener('input', () => {
    updateCounter();
    tasksInput.classList.remove('is-invalid');
  });
  updateCounter();

  energyInput.addEventListener('input', () => {
    energyOut.textContent = energyInput.value;
  });

  /** 시작 시각 기본값을 현재 시각(5분 단위 올림)으로 채운다. */
  function fillDefaultStartTime() {
    const now = new Date();
    now.setMinutes(Math.ceil(now.getMinutes() / 5) * 5, 0, 0);
    startTimeInput.value =
      String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
  }
  fillDefaultStartTime();

  resetBtn.addEventListener('click', () => {
    // reset 기본 동작이 끝난 뒤 값을 다시 세팅해야 한다.
    setTimeout(() => {
      updateCounter();
      energyOut.textContent = energyInput.value;
      fillDefaultStartTime();
      tasksInput.classList.remove('is-invalid');
      showState('idle');
    }, 0);
  });

  /* -------------------------------------------------------------------------
     결과 패널 상태 전환
     ------------------------------------------------------------------------- */
  function showState(name) {
    stateIdle.hidden = name !== 'idle';
    stateLoading.hidden = name !== 'loading';
    stateError.hidden = name !== 'error';
    stateSuccess.hidden = name !== 'success';
  }

  function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    submitBtn.classList.toggle('is-loading', isLoading);
    submitBtn.querySelector('.btn-label').textContent =
      isLoading ? '설계하는 중…' : '몰입 루틴 설계하기';
  }

  /* -------------------------------------------------------------------------
     오류 표시 — 코드별로 사용자 언어의 안내를 붙인다.
     ------------------------------------------------------------------------- */
  const ERROR_TEXT = {
    EMPTY_INPUT:   ['할 일을 입력해 주세요',      '오늘 처리할 일을 한 줄이라도 적어야 루틴을 만들 수 있습니다.', '예) 서론 초안 쓰기, 실험 데이터 정리'],
    TOO_SHORT:     ['조금만 더 적어 주세요',      '내용이 너무 짧아 작업을 이해하기 어렵습니다. 5자 이상 입력해 주세요.', ''],
    TOO_LONG:      ['입력이 너무 깁니다',         '할 일은 300자 이내로 줄여 주세요.', ''],
    INVALID_INPUT: ['입력값을 확인해 주세요',     '선택한 시간이나 컨디션 값이 올바르지 않습니다.', ''],
    RATE_LIMITED:  ['잠시 후 다시 시도해 주세요', '짧은 시간에 요청이 몰렸습니다. 30초 정도 뒤에 다시 눌러 주세요.', 'API 호출 한도를 보호하기 위한 제한입니다.'],
    NO_API_KEY:    ['AI 기능이 아직 설정되지 않았습니다', '서버에 API 키가 등록되어 있지 않습니다. 관리자에게 문의해 주세요.', 'Vercel 환경 변수(OPENAI_API_KEY 또는 GEMINI_API_KEY)를 확인하세요.'],
    UPSTREAM_AUTH: ['AI 서비스 인증에 실패했습니다', '서버에 등록된 API 키가 유효하지 않습니다.', '키가 만료되었거나 잘못 입력되었을 수 있습니다.'],
    UPSTREAM_QUOTA:['AI 사용량 한도를 초과했습니다', '잠시 후 다시 시도해 주세요. 계속되면 관리자에게 알려 주세요.', ''],
    UPSTREAM_ERROR:['AI 서비스가 불안정합니다',   '일시적인 오류입니다. 잠시 후 다시 시도해 주세요.', ''],
    PARSE_ERROR:   ['결과를 이해하지 못했습니다', 'AI 응답 형식이 예상과 달랐습니다. 다시 시도하면 대부분 해결됩니다.', ''],
    TIMEOUT:       ['응답이 너무 늦습니다',       '25초 안에 답을 받지 못해 요청을 중단했습니다. 잠시 후 다시 시도해 주세요.', '네트워크가 느리거나 AI 서버가 혼잡할 수 있습니다.'],
    NETWORK:       ['네트워크에 연결할 수 없습니다', '인터넷 연결 상태를 확인한 뒤 다시 시도해 주세요.', ''],
    UNKNOWN:       ['문제가 발생했습니다',        '알 수 없는 오류입니다. 잠시 후 다시 시도해 주세요.', '']
  };

  function showError(code, serverMessage) {
    const known = ERROR_TEXT[code];
    const [title, message, hint] = known || ERROR_TEXT.UNKNOWN;
    errorTitle.textContent = title;
    // 아는 코드면 "다음에 무엇을 하면 되는지"까지 담긴 안내문을 쓰고,
    // 모르는 코드일 때만 서버가 준 문구를 그대로 보여 준다.
    errorMessage.textContent = known ? message : (serverMessage || message);
    errorHint.textContent = hint;
    errorHint.hidden = !hint;
    // 사용자가 고칠 수 있는 입력 오류라면 재시도 대신 입력칸으로 보낸다.
    const isInputIssue = ['EMPTY_INPUT', 'TOO_SHORT', 'TOO_LONG', 'INVALID_INPUT'].includes(code);
    retryBtn.textContent = isInputIssue ? '입력 수정하기' : '다시 시도';
    retryBtn.dataset.mode = isInputIssue ? 'focus' : 'retry';
    showState('error');
  }

  retryBtn.addEventListener('click', () => {
    if (retryBtn.dataset.mode === 'focus') {
      tasksInput.focus();
      tasksInput.classList.add('is-invalid');
      showState('idle');
      return;
    }
    if (lastPayload) requestRoutine(lastPayload);
  });

  /* -------------------------------------------------------------------------
     폼 제출 → 요청
     ------------------------------------------------------------------------- */
  form.addEventListener('submit', (event) => {
    event.preventDefault();

    const tasks = tasksInput.value.trim();

    // (1) 빈 입력 — 서버까지 가지 않고 바로 막는다.
    if (!tasks) {
      tasksInput.classList.add('is-invalid');
      tasksInput.focus();
      showError('EMPTY_INPUT');
      toast('오늘 할 일을 먼저 입력해 주세요');
      return;
    }
    // (2) 너무 짧은 입력
    if (tasks.length < 5) {
      tasksInput.classList.add('is-invalid');
      tasksInput.focus();
      showError('TOO_SHORT');
      return;
    }

    const payload = {
      tasks: tasks,
      minutes: Number(minutesInput.value),
      startTime: startTimeInput.value || null,
      energy: Number(energyInput.value),
      workType: ($$('input[name="workType"]').find((r) => r.checked) || {}).value || '기타 사무',
      blocker: blockerInput.value.trim()
    };

    requestRoutine(payload);
  });

  async function requestRoutine(payload) {
    lastPayload = payload;

    // 이전 요청이 남아 있으면 취소한다. (버튼 연타 대비)
    if (inFlight) inFlight.abort();
    const controller = new AbortController();
    inFlight = controller;

    setLoading(true);
    showState('loading');
    loadingHint.textContent = '보통 5~10초 정도 걸립니다.';

    // 응답이 느릴 때 안내 문구를 바꿔 "멈춘 것처럼" 보이지 않게 한다.
    const slowTimer = setTimeout(() => {
      loadingHint.textContent = '조금 더 걸리고 있습니다. 잠시만 기다려 주세요…';
    }, SLOW_HINT_MS);

    // 지연/타임아웃 처리: 25초가 지나면 요청을 강제로 끊는다.
    // (AbortSignal.reason 은 구형 브라우저에 없어 별도 플래그로 원인을 기억한다.)
    let timedOut = false;
    const timeoutTimer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, TIMEOUT_MS);

    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
      });

      // 응답 본문이 JSON 이 아닐 수도 있으므로 안전하게 파싱한다.
      let body = null;
      try {
        body = await response.json();
      } catch (e) {
        body = null;
      }

      if (!response.ok || !body || body.ok !== true) {
        const code = (body && body.error && body.error.code) || httpStatusToCode(response.status);
        const message = body && body.error ? body.error.message : '';
        showError(code, message);
        return;
      }

      renderResult(body.data, payload);
      saveHistory(body.data, payload);
      toast('몰입 루틴을 설계했습니다');
    } catch (error) {
      if (error && error.name === 'AbortError') {
        // 사용자가 새 요청을 눌러 취소된 경우에는 오류를 띄우지 않는다.
        if (timedOut) showError('TIMEOUT');
        return;
      }
      showError('NETWORK');
    } finally {
      clearTimeout(slowTimer);
      clearTimeout(timeoutTimer);
      if (inFlight === controller) {
        inFlight = null;
        setLoading(false);
      }
    }
  }

  /** 서버가 JSON 오류 본문을 못 준 경우 HTTP 상태 코드로 원인을 추정한다. */
  function httpStatusToCode(status) {
    if (status === 400) return 'INVALID_INPUT';
    if (status === 429) return 'RATE_LIMITED';
    if (status === 504) return 'TIMEOUT';
    if (status >= 500) return 'UPSTREAM_ERROR';
    if (status >= 400) return 'INVALID_INPUT';
    return 'UNKNOWN';
  }

  /* -------------------------------------------------------------------------
     결과 렌더링
     ------------------------------------------------------------------------- */
  function renderResult(data, payload) {
    resultHeadline.textContent = data.headline || '오늘의 몰입 설계';
    resultStrategy.textContent = data.strategy || '';
    resultStrategy.hidden = !data.strategy;

    const totalFocus = (data.blocks || [])
      .filter((block) => block.type === 'focus')
      .reduce((sum, block) => sum + (block.duration_min || 0), 0);
    resultMeta.textContent =
      `총 ${payload.minutes}분 · 집중 ${totalFocus}분 · ${data.blocks.length}개 블록`;

    // --- 타임라인 ---
    timeline.textContent = '';
    (data.blocks || []).forEach((block, index) => {
      const item = document.createElement('li');
      item.className = 'tl-item' + (block.type === 'break' ? ' is-break' : '');
      item.style.animationDelay = (index * 60) + 'ms';

      const top = document.createElement('div');
      top.className = 'tl-top';

      const time = document.createElement('span');
      time.className = 'tl-time';
      time.textContent = `${block.start} – ${block.end}`;

      const badge = document.createElement('span');
      badge.className = 'tl-badge';
      badge.textContent = block.type === 'break' ? '회복' : '집중';

      const duration = document.createElement('span');
      duration.className = 'tl-dur';
      duration.textContent = `${block.duration_min}분`;

      top.append(time, badge, duration);

      const title = document.createElement('div');
      title.className = 'tl-title';
      title.textContent = block.title || '';

      item.append(top, title);

      if (block.goal) {
        const goal = document.createElement('p');
        goal.className = 'tl-goal';
        goal.textContent = '완료 기준 · ' + block.goal;
        item.append(goal);
      }
      if (block.tip) {
        const tip = document.createElement('p');
        tip.className = 'tl-tip';
        tip.textContent = block.tip;
        item.append(tip);
      }
      timeline.append(item);
    });

    // --- 체크리스트 ---
    resultChecklist.textContent = '';
    (data.checklist || []).forEach((text) => {
      const li = document.createElement('li');
      li.append(document.createTextNode(text));
      resultChecklist.append(li);
    });

    resultCaution.textContent = data.caution || '무리하지 말고 컨디션에 맞춰 조정하세요.';

    showState('success');
  }

  /* -------------------------------------------------------------------------
     결과 텍스트 복사
     ------------------------------------------------------------------------- */
  copyBtn.addEventListener('click', async () => {
    const lines = [resultHeadline.textContent, ''];
    if (resultStrategy.textContent) lines.push(resultStrategy.textContent, '');

    $$('.tl-item', timeline).forEach((item) => {
      const time = $('.tl-time', item).textContent;
      const title = $('.tl-title', item).textContent;
      const goal = $('.tl-goal', item);
      lines.push(`${time}  ${title}${goal ? ' (' + goal.textContent + ')' : ''}`);
    });

    lines.push('', '[마무리 체크]');
    $$('li', resultChecklist).forEach((li) => lines.push('- ' + li.textContent));
    lines.push('', '주의: ' + resultCaution.textContent);

    const text = lines.join('\n');
    try {
      await navigator.clipboard.writeText(text);
      toast('설계 내용을 복사했습니다');
    } catch (e) {
      // 클립보드 권한이 없거나 http 환경일 때의 대체 경로
      const helper = document.createElement('textarea');
      helper.value = text;
      helper.setAttribute('readonly', '');
      helper.style.position = 'fixed';
      helper.style.opacity = '0';
      document.body.append(helper);
      helper.select();
      try {
        document.execCommand('copy');
        toast('설계 내용을 복사했습니다');
      } catch (err) {
        toast('복사에 실패했습니다. 직접 선택해 복사해 주세요');
      }
      helper.remove();
    }
  });

  /* -------------------------------------------------------------------------
     최근 설계 기록 (브라우저 localStorage — 서버에는 저장하지 않음)
     ------------------------------------------------------------------------- */
  function readHistory() {
    try {
      const raw = localStorage.getItem(HISTORY_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  function saveHistory(data, payload) {
    const entry = {
      at: new Date().toISOString(),
      headline: data.headline || '오늘의 몰입 설계',
      tasks: payload.tasks.slice(0, 80),
      minutes: payload.minutes
    };
    const list = [entry, ...readHistory()].slice(0, HISTORY_MAX);
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(list));
    } catch (e) {
      /* 저장 실패는 기능에 영향을 주지 않으므로 무시한다. */
    }
    renderHistory();
  }

  function renderHistory() {
    const list = readHistory();
    historyWrap.hidden = list.length === 0;
    historyList.textContent = '';

    list.forEach((entry) => {
      const li = document.createElement('li');
      li.className = 'history-item';

      const time = document.createElement('div');
      time.className = 'h-time';
      const date = new Date(entry.at);
      time.textContent = isNaN(date)
        ? ''
        : `${date.getMonth() + 1}월 ${date.getDate()}일 ` +
          `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}` +
          ` · ${entry.minutes}분`;

      const head = document.createElement('div');
      head.className = 'h-head';
      head.textContent = entry.headline;

      const tasks = document.createElement('div');
      tasks.className = 'h-tasks';
      tasks.textContent = entry.tasks;

      li.append(time, head, tasks);
      historyList.append(li);
    });
  }

  clearHistoryBtn.addEventListener('click', () => {
    try {
      localStorage.removeItem(HISTORY_KEY);
    } catch (e) { /* 무시 */ }
    renderHistory();
    toast('기록을 삭제했습니다');
  });

  renderHistory();
})();
