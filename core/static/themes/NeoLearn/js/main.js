// ===================================
// NeoLearn - Main JavaScript
// ===================================

document.addEventListener('DOMContentLoaded', function() {
  
  // ===================================
  // Theme Toggle
  // ===================================
  const themeToggle = document.getElementById('themeToggle');
  const html = document.documentElement;
  const sunIcon = themeToggle?.querySelector('.sun-icon');
  const moonIcon = themeToggle?.querySelector('.moon-icon');
  
  // Load saved theme or default to light
  const savedTheme = localStorage.getItem('theme') || 'light';
  html.setAttribute('data-theme', savedTheme);
  updateThemeIcon(savedTheme);
  
  themeToggle?.addEventListener('click', function() {
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
  });
  
  function updateThemeIcon(theme) {
    if (theme === 'dark') {
      sunIcon.style.display = 'none';
      moonIcon.style.display = 'block';
    } else {
      sunIcon.style.display = 'block';
      moonIcon.style.display = 'none';
    }
  }
  
  // ===================================
  // User Menu Dropdown
  // ===================================
  const userMenuToggle = document.getElementById('userMenuToggle');
  const userDropdown = document.getElementById('userDropdown');
  
  userMenuToggle?.addEventListener('click', function(e) {
    e.stopPropagation();
    userDropdown.classList.toggle('active');
  });
  
  // Close dropdown when clicking outside
  document.addEventListener('click', function(e) {
    if (userDropdown && !userMenuToggle?.contains(e.target)) {
      userDropdown.classList.remove('active');
    }
  });
  
  // ===================================
  // Mobile Menu Toggle
  // ===================================
  const menuToggle = document.getElementById('menuToggle');
  const sidebar = document.getElementById('sidebar');
  
  menuToggle?.addEventListener('click', function() {
    sidebar?.classList.toggle('active');
    
    // Animate hamburger icon
    const spans = this.querySelectorAll('span');
    spans[0].style.transform = sidebar?.classList.contains('active') 
      ? 'rotate(45deg) translateY(8px)' 
      : 'none';
    spans[1].style.opacity = sidebar?.classList.contains('active') ? '0' : '1';
    spans[2].style.transform = sidebar?.classList.contains('active') 
      ? 'rotate(-45deg) translateY(-8px)' 
      : 'none';
  });
  
  // Close sidebar when clicking outside on mobile
  document.addEventListener('click', function(e) {
    if (window.innerWidth <= 1024 && 
        sidebar?.classList.contains('active') && 
        !sidebar.contains(e.target) && 
        !menuToggle?.contains(e.target)) {
      sidebar.classList.remove('active');
      
      const spans = menuToggle.querySelectorAll('span');
      spans.forEach(span => {
        span.style.transform = 'none';
        span.style.opacity = '1';
      });
    }
  });
  
  // ===================================
  // Flash Messages Auto-dismiss
  // ===================================
  const flashMessages = document.querySelectorAll('.flash-messages .alert');
  
  flashMessages.forEach(function(message) {
    setTimeout(function() {
      message.style.opacity = '0';
      message.style.transform = 'translateY(-1rem)';
      
      setTimeout(function() {
        message.remove();
      }, 300);
    }, 5000);
  });
  
  // ===================================
  // Smooth Scroll for Anchor Links
  // ===================================
  document.querySelectorAll('a[href^="#"]').forEach(function(anchor) {
    anchor.addEventListener('click', function(e) {
      const href = this.getAttribute('href');
      if (href !== '#' && href !== '') {
        e.preventDefault();
        const target = document.querySelector(href);
        
        if (target) {
          target.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
          });
        }
      }
    });
  });
  
  // ===================================
  // Form Validation Helper
  // ===================================
  const forms = document.querySelectorAll('form[data-validate]');
  
  forms.forEach(function(form) {
    form.addEventListener('submit', function(e) {
      const inputs = form.querySelectorAll('input[required], textarea[required], select[required]');
      let isValid = true;
      
      inputs.forEach(function(input) {
        if (!input.value.trim()) {
          isValid = false;
          input.classList.add('error');
          
          // Remove error class on input
          input.addEventListener('input', function() {
            this.classList.remove('error');
          }, { once: true });
        }
      });
      
      if (!isValid) {
        e.preventDefault();
      }
    });
  });
  
  // ===================================
  // Card Hover Effect
  // ===================================
  const cards = document.querySelectorAll('.course-card, .stat-card');
  
  cards.forEach(function(card) {
    card.addEventListener('mouseenter', function() {
      this.style.transform = 'translateY(-4px)';
    });
    
    card.addEventListener('mouseleave', function() {
      this.style.transform = 'translateY(0)';
    });
  });
  
  // ===================================
  // Progress Bar Animation
  // ===================================
  const progressBars = document.querySelectorAll('.progress-fill');
  
  const observerOptions = {
    threshold: 0.5,
    rootMargin: '0px'
  };
  
  const progressObserver = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
      if (entry.isIntersecting) {
        const width = entry.target.style.width;
        entry.target.style.width = '0%';
        
        setTimeout(function() {
          entry.target.style.width = width;
        }, 100);
        
        progressObserver.unobserve(entry.target);
      }
    });
  }, observerOptions);
  
  progressBars.forEach(function(bar) {
    progressObserver.observe(bar);
  });
  
  // ===================================
  // Search Functionality
  // ===================================
  const searchInput = document.querySelector('.search-bar input');
  
  searchInput?.addEventListener('input', function(e) {
    const query = e.target.value.toLowerCase();
    
    // You can implement search filtering here
    // This is just a placeholder for demonstration
    if (query.length > 2) {
      console.log('Searching for:', query);
    }
  });
  
  // ===================================
  // Tooltip Initialization
  // ===================================
  const tooltipElements = document.querySelectorAll('[data-tooltip]');
  
  tooltipElements.forEach(function(element) {
    element.addEventListener('mouseenter', function() {
      const tooltipText = this.getAttribute('data-tooltip');
      const tooltip = document.createElement('div');
      
      tooltip.className = 'tooltip';
      tooltip.textContent = tooltipText;
      document.body.appendChild(tooltip);
      
      const rect = this.getBoundingClientRect();
      tooltip.style.top = (rect.top - tooltip.offsetHeight - 8) + 'px';
      tooltip.style.left = (rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2)) + 'px';
      
      this._tooltip = tooltip;
    });
    
    element.addEventListener('mouseleave', function() {
      if (this._tooltip) {
        this._tooltip.remove();
        this._tooltip = null;
      }
    });
  });
  
  // ===================================
  // Notification Badge Update
  // ===================================
  function updateNotificationBadge(count) {
    const badge = document.querySelector('.notifications .badge');
    if (badge) {
      badge.textContent = count;
      badge.style.display = count > 0 ? 'flex' : 'none';
    }
  }
  
  // Example: updateNotificationBadge(5);
  
  // ===================================
  // Keyboard Shortcuts
  // ===================================
  document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + K: Focus search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      searchInput?.focus();
    }
    
    // Escape: Close modals/dropdowns
    if (e.key === 'Escape') {
      userDropdown?.classList.remove('active');
      sidebar?.classList.remove('active');
    }
  });
  
  // ===================================
  // Console Welcome Message
  // ===================================
  console.log('%c🎓 NeoLearn', 'font-size: 24px; font-weight: bold; color: #667eea;');
  console.log('%cPowered by modern web technologies', 'color: #6b7280;');
  
});

// ===================================
// Utility Functions
// ===================================

// Format date
function formatDate(date) {
  return new Intl.DateTimeFormat('pt-BR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  }).format(date);
}

// Debounce function
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// Throttle function
function throttle(func, limit) {
  let inThrottle;
  return function(...args) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

// ABRIR MODAL GENÉRICO PARA CONFIRMAR A EXCLUSÃO
function openConfirmDelete(button) {
    const url = button.getAttribute('data-url');
    const message = button.getAttribute('data-message');
    const title = button.getAttribute('title');

    const form = document.getElementById('confirmModalForm');
    form.action = url;

    openConfirmModal(
      message,            // mensagem principal
      'confirmModalForm', // id do form
      title,              // título do modal
      'Confirmar'         // texto do botão confirmar
    );
}

// ===== ABRIR MODAL GENÉRICO =====
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden'; // bloqueia scroll de fundo
  }
}

// ===== FECHAR MODAL GENÉRICO =====
function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = ''; // libera scroll novamente
  }
}

// ===== FECHAR AO CLICAR FORA =====
document.addEventListener('click', (e) => {
  // se o elemento clicado tem a classe "modal-overlay"
  if (e.target.classList.contains('modal-overlay')) {
    const modal = e.target.closest('.modal');
    if (modal) {
      modal.classList.remove('active');
      document.body.style.overflow = '';
    }
  }
});

// ===== FECHAR AO PRESSIONAR ESC =====
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const modals = document.querySelectorAll('.modal.active');
    modals.forEach((modal) => {
      modal.classList.remove('active');
    });
    document.body.style.overflow = '';
  }
});





