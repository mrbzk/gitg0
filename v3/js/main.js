// gittgo: shared site behaviour

document.addEventListener('DOMContentLoaded', () => {

  // Mobile menu toggle
  const burger = document.querySelector('.burger');
  const mobileMenu = document.querySelector('.mobile-menu');
  const mobileClose = document.querySelector('.mobile-menu-close');
  if (burger && mobileMenu) {
    burger.addEventListener('click', () => mobileMenu.classList.add('open'));
  }
  if (mobileClose && mobileMenu) {
    mobileClose.addEventListener('click', () => mobileMenu.classList.remove('open'));
  }
  if (mobileMenu) {
    // Close the mobile menu on any link click. Page-navigation links unload
    // the page anyway, but same-page anchor links (e.g. "#journey") don't,
    // so without this the full-screen overlay would stay up over the target
    // section instead of revealing the scroll.
    mobileMenu.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => mobileMenu.classList.remove('open'));
    });
  }

  // Desktop dropdown (click-to-toggle, keyboard accessible; hover handled in CSS)
  document.querySelectorAll('.nav-drop-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const parent = btn.closest('.nav-drop');
      document.querySelectorAll('.nav-drop.open').forEach(d => { if (d !== parent) d.classList.remove('open'); });
      parent.classList.toggle('open');
    });
  });
  document.addEventListener('click', () => {
    document.querySelectorAll('.nav-drop.open').forEach(d => d.classList.remove('open'));
  });

  // FAQ accordion
  document.querySelectorAll('.faq-item').forEach(item => {
    const q = item.querySelector('.faq-q');
    if (!q) return;
    q.addEventListener('click', () => {
      const isOpen = item.classList.contains('open');
      item.parentElement.querySelectorAll('.faq-item').forEach(i => i.classList.remove('open'));
      if (!isOpen) item.classList.add('open');
    });
  });

  // Scroll reveal
  const revealEls = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window && revealEls.length) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('visible'); });
    }, { threshold: 0.12 });
    revealEls.forEach(el => io.observe(el));
  } else {
    revealEls.forEach(el => el.classList.add('visible'));
  }

  // Static-site form handling (MVP placeholder, wire to real backend/CRM before launch)
  document.querySelectorAll('form[data-form]').forEach(form => {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const card = form.closest('.form-card');
      const success = card ? card.parentElement.querySelector('.form-success') : null;
      if (form) form.style.display = 'none';
      if (success) success.classList.add('visible');
    });
  });

  // Click-to-play video embeds: shows a real YouTube thumbnail + play
  // button (set via inline style/data attribute in the page) and only
  // creates the actual iframe once someone clicks or presses Enter/Space,
  // instead of loading YouTube's iframe for everyone up front.
  document.querySelectorAll('.video-embed[data-yt-id]').forEach(el => {
    const play = () => {
      if (el.classList.contains('is-playing')) return;
      const id = el.getAttribute('data-yt-id');
      const iframe = document.createElement('iframe');
      iframe.src = `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0`;
      iframe.title = el.getAttribute('aria-label') || 'YouTube video';
      iframe.setAttribute('allow', 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture');
      iframe.allowFullscreen = true;
      el.appendChild(iframe);
      el.classList.add('is-playing');
    };
    el.addEventListener('click', play);
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); play(); }
    });
  });

  // Photo grid lightbox: clicking a thumbnail opens the full-size photo
  // in an overlay instead of navigating to it. The <a href="..."> still
  // points at the full image, so this degrades gracefully (opens the
  // image directly) if JS fails to load for any reason.
  const lightbox = document.getElementById('lightbox');
  if (lightbox) {
    const lightboxImg = lightbox.querySelector('.lightbox-img');
    const openLightbox = (href, alt) => {
      lightboxImg.src = href;
      lightboxImg.alt = alt || '';
      lightbox.classList.add('open');
      lightbox.setAttribute('aria-hidden', 'false');
    };
    const closeLightbox = () => {
      lightbox.classList.remove('open');
      lightbox.setAttribute('aria-hidden', 'true');
      lightboxImg.src = '';
    };
    document.querySelectorAll('.photo-grid a').forEach(a => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        const img = a.querySelector('img');
        openLightbox(a.getAttribute('href'), img ? img.alt : '');
      });
    });
    lightbox.querySelector('.lightbox-close').addEventListener('click', closeLightbox);
    lightbox.addEventListener('click', (e) => { if (e.target === lightbox) closeLightbox(); });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && lightbox.classList.contains('open')) closeLightbox();
    });
  }

  // Progressive Concierge request form: reveals one question at a time
  // instead of showing every field at once, per the Concierge page brief.
  document.querySelectorAll('.pf-card').forEach(card => {
    const form = card.querySelector('form');
    if (!form) return;
    const steps = Array.from(form.querySelectorAll('.pf-step'));
    const progressBar = card.querySelector('.pf-progress-bar');
    let current = 0;

    const showStep = (i) => {
      steps.forEach((s, idx) => s.classList.toggle('active', idx === i));
      if (progressBar) progressBar.style.width = ((i + 1) / steps.length * 100) + '%';
      current = i;
      const firstField = steps[i].querySelector('input, textarea');
      if (firstField) firstField.focus({ preventScroll: true });
    };

    // Standard UK postcode pattern (covers all current formats, e.g. IP3 9BF, SW1A 1AA, M1 1AE).
    const ukPostcodeRegex = /^[A-Za-z]{1,2}[0-9Rr][0-9A-Za-z]?\s?[0-9][A-Za-z]{2}$/;

    const stepIsValid = (stepEl, validate) => {
      if (validate === 'postcode') {
        const postcodeInput = stepEl.querySelector('input[name="postcode"]');
        const errorEl = stepEl.querySelector('.pf-error');
        const value = postcodeInput ? postcodeInput.value.trim() : '';
        const valid = !!value && ukPostcodeRegex.test(value);
        if (errorEl) errorEl.hidden = valid;
        if (!valid && postcodeInput) postcodeInput.focus();
        return valid;
      }
      if (validate === 'contact') {
        const checked = stepEl.querySelector('input[name="contactPref"]:checked');
        return !!checked;
      }
      const requiredFields = stepEl.querySelectorAll('[required]');
      for (const field of requiredFields) {
        if (!field.value || !field.value.trim()) { field.focus(); return false; }
      }
      return true;
    };

    form.querySelectorAll('[data-pf-next]').forEach(btn => {
      btn.addEventListener('click', () => {
        const stepEl = steps[current];
        if (!stepIsValid(stepEl, btn.getAttribute('data-pf-validate'))) return;
        if (current < steps.length - 1) showStep(current + 1);
      });
    });

    form.querySelectorAll('[data-pf-back]').forEach(btn => {
      btn.addEventListener('click', () => { if (current > 0) showStep(current - 1); });
    });

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      if (!stepIsValid(steps[current])) return;
      form.style.display = 'none';
      const progress = card.querySelector('.pf-progress');
      if (progress) progress.style.display = 'none';
      const success = card.querySelector('.pf-success');
      if (success) success.classList.add('visible');
      success && success.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });

    showStep(0);
  });

  // Sticky mobile "Request Concierge" bar: hide it once the real
  // progressive request form is already on screen, so it doesn't sit
  // on top of the very form it links to.
  const stickyBar = document.querySelector('.sticky-concierge-bar');
  const requestSection = document.getElementById('request');
  if (stickyBar && requestSection) {
    document.body.classList.add('has-sticky-bar');
    if ('IntersectionObserver' in window) {
      const ioSticky = new IntersectionObserver((entries) => {
        entries.forEach(e => { stickyBar.style.display = e.isIntersecting ? 'none' : ''; });
      }, { threshold: 0.15 });
      ioSticky.observe(requestSection);
    }
  }

});
