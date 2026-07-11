const navToggle = document.querySelector('[data-nav-toggle]');
const nav = document.querySelector('[data-nav]');
const videoModal = document.querySelector('[data-video-modal]');
const video = videoModal?.querySelector('video');
const openVideoButtons = document.querySelectorAll('[data-open-video]');
const closeVideoButtons = document.querySelectorAll('[data-close-video]');
const year = document.querySelector('[data-year]');

if (year) year.textContent = new Date().getFullYear();

navToggle?.addEventListener('click', () => {
  const isOpen = nav?.classList.toggle('is-open');
  navToggle.setAttribute('aria-expanded', String(Boolean(isOpen)));
});

nav?.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => {
    nav?.classList.remove('is-open');
    navToggle?.setAttribute('aria-expanded', 'false');
  });
});

function openVideo() {
  if (!videoModal) return;
  videoModal.hidden = false;
  document.body.style.overflow = 'hidden';
  video?.focus();
}

function closeVideo() {
  if (!videoModal) return;
  videoModal.hidden = true;
  document.body.style.overflow = '';
  if (video) {
    video.pause();
    video.currentTime = 0;
  }
}

openVideoButtons.forEach((button) => button.addEventListener('click', openVideo));
closeVideoButtons.forEach((button) => button.addEventListener('click', closeVideo));

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && videoModal && !videoModal.hidden) closeVideo();
});

const reveals = document.querySelectorAll('.reveal');
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.12 });

reveals.forEach((el) => revealObserver.observe(el));
