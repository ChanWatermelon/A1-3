/* ===========================================================================
   main.js — 페이지 공통 UI 동작
     1. 다크 모드 전환 (localStorage 기억)
     2. 모바일 메뉴 열기/닫기
     3. 스크롤 위치에 따른 헤더/네비게이션 활성 표시
     4. 스크롤 등장 애니메이션
     5. 공용 토스트 알림  (window.Molip.toast 로 다른 스크립트에서 사용)
   =========================================================================== */

(function () {
  'use strict';

  /** 자주 쓰는 선택자 헬퍼 */
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

  /* -------------------------------------------------------------------------
     1. 다크 모드
     ------------------------------------------------------------------------- */
  const THEME_KEY = 'molip-theme';
  const themeToggle = $('#themeToggle');

  /** 현재 화면에 적용 중인 테마를 반환한다. (직접 지정 > 시스템 설정) */
  function currentTheme() {
    const explicit = document.documentElement.getAttribute('data-theme');
    if (explicit === 'dark' || explicit === 'light') return explicit;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (e) {
      /* 저장이 막힌 환경이어도 현재 세션에는 적용되므로 무시한다. */
    }
    const meta = $('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'dark' ? '#131320' : '#4c3bcf');
  }

  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const next = currentTheme() === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      toast(next === 'dark' ? '다크 모드로 전환했습니다' : '라이트 모드로 전환했습니다');
    });
  }

  /* -------------------------------------------------------------------------
     2. 모바일 메뉴
     ------------------------------------------------------------------------- */
  const navToggle = $('#navToggle');
  const siteNav = $('#siteNav');

  function closeNav() {
    if (!siteNav || !navToggle) return;
    siteNav.classList.remove('is-open');
    navToggle.setAttribute('aria-expanded', 'false');
    navToggle.setAttribute('aria-label', '메뉴 열기');
  }

  if (navToggle && siteNav) {
    navToggle.addEventListener('click', () => {
      const willOpen = !siteNav.classList.contains('is-open');
      siteNav.classList.toggle('is-open', willOpen);
      navToggle.setAttribute('aria-expanded', String(willOpen));
      navToggle.setAttribute('aria-label', willOpen ? '메뉴 닫기' : '메뉴 열기');
    });

    // 메뉴 항목을 누르면 이동 후 자동으로 닫는다.
    $$('.nav-link', siteNav).forEach((link) => link.addEventListener('click', closeNav));

    // 바깥 영역 클릭 / ESC 로도 닫는다.
    document.addEventListener('click', (event) => {
      if (!siteNav.classList.contains('is-open')) return;
      if (siteNav.contains(event.target) || navToggle.contains(event.target)) return;
      closeNav();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeNav();
    });
    // 데스크톱 폭으로 넓어지면 모바일 메뉴 상태를 초기화한다.
    window.matchMedia('(min-width: 761px)').addEventListener('change', closeNav);
  }

  /* -------------------------------------------------------------------------
     3. 헤더 그림자 + 현재 섹션 메뉴 강조
     ------------------------------------------------------------------------- */
  const header = $('#siteHeader');
  const navLinks = $$('.site-nav .nav-link');
  const sections = navLinks
    .map((link) => document.getElementById(link.getAttribute('href').slice(1)))
    .filter(Boolean);

  function onScroll() {
    if (header) header.classList.toggle('is-scrolled', window.scrollY > 8);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  if ('IntersectionObserver' in window && sections.length) {
    const spy = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          navLinks.forEach((link) => {
            link.classList.toggle(
              'is-active',
              link.getAttribute('href') === '#' + entry.target.id
            );
          });
        });
      },
      // 화면 상단 30% 지점을 지나는 섹션을 "현재 섹션"으로 본다.
      { rootMargin: '-30% 0px -60% 0px', threshold: 0 }
    );
    sections.forEach((section) => spy.observe(section));
  }

  /* -------------------------------------------------------------------------
     4. 스크롤 등장 애니메이션
     ------------------------------------------------------------------------- */
  const revealTargets = $$('.reveal');
  if ('IntersectionObserver' in window && revealTargets.length) {
    const revealer = new IntersectionObserver(
      (entries, observer) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target); // 한 번만 실행
        });
      },
      { threshold: 0.12 }
    );
    revealTargets.forEach((element) => revealer.observe(element));
  } else {
    // IntersectionObserver 미지원 브라우저에서는 즉시 보이게 한다.
    revealTargets.forEach((element) => element.classList.add('is-visible'));
  }

  /* -------------------------------------------------------------------------
     5. 토스트 알림
     ------------------------------------------------------------------------- */
  const toastElement = $('#toast');
  let toastTimer = null;

  function toast(message, duration = 2200) {
    if (!toastElement) return;
    toastElement.textContent = message;
    toastElement.hidden = false;
    // hidden 해제 직후 클래스를 붙여야 전환 애니메이션이 동작한다.
    requestAnimationFrame(() => toastElement.classList.add('is-visible'));

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastElement.classList.remove('is-visible');
      setTimeout(() => { toastElement.hidden = true; }, 260);
    }, duration);
  }

  /* -------------------------------------------------------------------------
     다른 스크립트(routine.js / contact.js)에서 쓸 공용 도구 노출
     ------------------------------------------------------------------------- */
  window.Molip = {
    $,
    $$,
    toast,
    currentTheme
  };
})();
