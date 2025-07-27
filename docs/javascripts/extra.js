/* docs/javascripts/extra.js - Melhorias Interativas Loczcit-IQR */

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Loczcit-IQR - Documentação Profissional Carregada');
    
    // Inicializar todas as funcionalidades
    initMathJax();
    initCodeEnhancements();
    initImageEnhancements();
    initSmoothScrolling();
    initAnalytics();
    initPerformanceOptimizations();
    initAccessibilityFeatures();
    
    // Animações de entrada
    setTimeout(() => {
        animateOnLoad();
    }, 100);
});

// ========== CONFIGURAÇÃO MATHJAX ==========
function initMathJax() {
    window.MathJax = {
        tex: {
            inlineMath: [['$', '$'], ['\\(', '\\)']],
            displayMath: [['$$', '$$'], ['\\[', '\\]']],
            processEscapes: true,
            processEnvironments: true,
            tags: 'ams',
            macros: {
                'ZCIT': '\\text{ZCIT}',
                'ROL': '\\text{ROL}',
                'IQR': '\\text{IQR}',
                'Q1': 'Q_1',
                'Q3': 'Q_3',
                'LI': '\\text{LI}',
                'LS': '\\text{LS}',
                'Wm': '\\text{W}\\,\\text{m}^{-2}',
                'hPa': '\\text{hPa}',
                'ms': '\\text{m}\\,\\text{s}^{-1}'
            }
        },
        options: {
            ignoreHtmlClass: 'tex2jax_ignore',
            processHtmlClass: 'tex2jax_process'
        },
        startup: {
            ready: () => {
                console.log('📐 MathJax configurado para Loczcit-IQR');
                MathJax.startup.defaultReady();
            }
        }
    };
}

// ========== MELHORIAS DE CÓDIGO ==========
function initCodeEnhancements() {
    document.querySelectorAll('pre code').forEach(function(block) {
        if (block.textContent.split('\n').length > 10) {
            block.classList.add('line-numbers');
        }
        
        const language = block.className.match(/language-(\w+)/);
        if (language) {
            addLanguageLabel(block, language[1]);
        }
    });
    
    enhanceCopyButtons();
}

function addLanguageLabel(codeBlock, language) {
    const pre = codeBlock.closest('pre');
    if (pre && !pre.querySelector('.language-label')) {
        const label = document.createElement('span');
        label.className = 'language-label';
        label.textContent = language.toUpperCase();
        pre.style.position = 'relative';
        pre.appendChild(label);
        
        label.style.cssText = `
            position: absolute;
            top: 8px;
            right: 12px;
            background: var(--accent-gold);
            color: var(--text-on-primary);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            z-index: 1;
        `;
    }
}

function enhanceCopyButtons() {
    document.querySelectorAll('.md-clipboard').forEach(function(button) {
        button.addEventListener('click', function() {
            const originalText = button.title;
            button.title = '✅ Copiado!';
            button.style.color = 'var(--accent-gold)';
            
            setTimeout(() => {
                button.title = originalText;
                button.style.color = '';
            }, 2000);
        });
    });
}

// ========== MELHORIAS DE IMAGEM ==========
function initImageEnhancements() {
    document.querySelectorAll('img').forEach(function(img) {
        if (!img.loading) {
            img.loading = 'lazy';
        }
        
        if (img.naturalWidth > 800 || img.alt.includes('Figura')) {
            addImageZoom(img);
        }
        
        if (!img.alt) {
            img.alt = 'Imagem da documentação Loczcit-IQR';
        }
    });
}

function addImageZoom(img) {
    img.style.cursor = 'zoom-in';
    img.addEventListener('click', function() {
        createImageModal(this);
    });
}

function createImageModal(img) {
    const modal = document.createElement('div');
    modal.className = 'image-modal';
    modal.innerHTML = `
        <div class="modal-backdrop">
            <div class="modal-content">
                <button class="modal-close" aria-label="Fechar">&times;</button>
                <img src="${img.src}" alt="${img.alt}" style="max-width: 90vw; max-height: 90vh;">
                <div class="modal-caption">${img.alt}</div>
            </div>
        </div>
    `;
    
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.9);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
        animation: fadeIn 0.3s ease-out;
    `;
    
    const backdrop = modal.querySelector('.modal-backdrop');
    backdrop.style.cssText = `
        position: relative;
        max-width: 95%;
        max-height: 95%;
        text-align: center;
    `;
    
    const closeBtn = modal.querySelector('.modal-close');
    closeBtn.style.cssText = `
        position: absolute;
        top: -40px;
        right: -40px;
        background: var(--accent-gold);
        color: var(--text-on-primary);
        border: none;
        border-radius: 50%;
        width: 32px;
        height: 32px;
        font-size: 20px;
        cursor: pointer;
        z-index: 10000;
    `;
    
    const caption = modal.querySelector('.modal-caption');
    caption.style.cssText = `
        margin-top: 16px;
        color: white;
        font-size: 0.875rem;
        max-width: 600px;
        margin-left: auto;
        margin-right: auto;
    `;
    
    document.body.appendChild(modal);
    document.body.style.overflow = 'hidden';
    
    closeBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', function(e) {
        if (e.target === modal) closeModal();
    });
    
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeModal();
    });
    
    function closeModal() {
        modal.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => {
            document.body.removeChild(modal);
            document.body.style.overflow = '';
        }, 300);
    }
}

// ========== SCROLL SUAVE ==========
function initSmoothScrolling() {
    document.querySelectorAll('a[href^="#"]').forEach(function(link) {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            const targetElement = document.querySelector(targetId);
            
            if (targetElement) {
                targetElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
                
                window.history.pushState(null, null, targetId);
            }
        });
    });
}

// ========== ANALYTICS E TRACKING ==========
function initAnalytics() {
    trackCodeCopies();
    trackDownloads();
    trackExternalLinks();
}

function trackCodeCopies() {
    document.querySelectorAll('.md-clipboard').forEach(function(button) {
        button.addEventListener('click', function() {
            if (typeof gtag !== 'undefined') {
                gtag('event', 'code_copy', {
                    event_category: 'engagement',
                    event_label: 'loczcit_documentation'
                });
            }
        });
    });
}

function trackDownloads() {
    document.querySelectorAll('a[href$=".pdf"], a[href$=".zip"], a[href$=".tar.gz"]').forEach(function(link) {
        link.addEventListener('click', function() {
            if (typeof gtag !== 'undefined') {
                gtag('event', 'file_download', {
                    event_category: 'downloads',
                    event_label: this.href.split('/').pop()
                });
            }
        });
    });
}

function trackExternalLinks() {
    document.querySelectorAll('a[href^="http"]:not([href*="' + window.location.hostname + '"])').forEach(function(link) {
        link.addEventListener('click', function() {
            if (typeof gtag !== 'undefined') {
                gtag('event', 'click', {
                    event_category: 'outbound',
                    event_label: this.href,
                    transport_type: 'beacon'
                });
            }
        });
    });
}

// ========== OTIMIZAÇÕES DE PERFORMANCE ==========
function initPerformanceOptimizations() {
    preloadImportantPages();
    optimizeAnimations();
    initLazyLoading();
}

function preloadImportantPages() {
    const importantPages = [
        '/getting-started/installation/',
        '/guides/user-guide/',
        '/api/reference/'
    ];
    
    importantPages.forEach(function(page) {
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = page;
        document.head.appendChild(link);
    });
}

function optimizeAnimations() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        document.documentElement.style.setProperty('--transition-fast', '0ms');
        document.documentElement.style.setProperty('--transition-base', '0ms');
        document.documentElement.style.setProperty('--transition-slow', '0ms');
    }
}

function initLazyLoading() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '50px'
    };
    
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate-in');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);
    
    document.querySelectorAll('.md-typeset h2, .md-typeset .admonition, .md-typeset table').forEach(function(el) {
        observer.observe(el);
    });
}

// ========== ACESSIBILIDADE ==========
function initAccessibilityFeatures() {
    enhanceKeyboardNavigation();
    addSkipLinks();
    enhanceHighContrast();
}

function enhanceKeyboardNavigation() {
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Tab') {
            document.body.classList.add('keyboard-navigation');
        }
    });
    
    document.addEventListener('mousedown', function() {
        document.body.classList.remove('keyboard-navigation');
    });
}

function addSkipLinks() {
    const skipLink = document.createElement('a');
    skipLink.href = '#content';
    skipLink.textContent = 'Pular para o conteúdo principal';
    skipLink.className = 'skip-link';
    skipLink.style.cssText = `
        position: absolute;
        top: -40px;
        left: 6px;
        background: var(--primary-blue);
        color: white;
        padding: 8px;
        border-radius: 4px;
        text-decoration: none;
        z-index: 10000;
        transition: top 0.2s;
    `;
    
    skipLink.addEventListener('focus', function() {
        this.style.top = '6px';
    });
    
    skipLink.addEventListener('blur', function() {
        this.style.top = '-40px';
    });
    
    document.body.insertBefore(skipLink, document.body.firstChild);
}

function enhanceHighContrast() {
    if (window.matchMedia('(prefers-contrast: high)').matches) {
        document.documentElement.classList.add('high-contrast');
    }
}

// ========== ANIMAÇÕES DE ENTRADA ==========
function animateOnLoad() {
    const content = document.querySelector('.md-content');
    if (content) {
        content.style.opacity = '0';
        content.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            content.style.transition = 'opacity 0.6s ease-out, transform 0.6s ease-out';
            content.style.opacity = '1';
            content.style.transform = 'translateY(0)';
        }, 50);
    }
    
    document.querySelectorAll('.md-nav__link').forEach(function(link, index) {
        link.style.opacity = '0';
        link.style.transform = 'translateX(-20px)';
        
        setTimeout(() => {
            link.style.transition = 'opacity 0.4s ease-out, transform 0.4s ease-out';
            link.style.opacity = '1';
            link.style.transform = 'translateX(0)';
        }, index * 50);
    });
}

// ========== TOOLTIPS SEGUROS ==========
function initTooltips() {
    const technicalTerms = {
        'ZCIT': 'Zona de Convergência Intertropical - Sistema meteorológico que regula as chuvas tropicais',
        'IQR': 'Intervalo Interquartílico - Método estatístico para detecção de outliers',
        'ROL': 'Radiação de Onda Longa - Medida da energia térmica emitida pela Terra',
        'B-Spline': 'Curva paramétrica suave usada para interpolação matemática',
        'Pentada': 'Período de 5 dias consecutivos usado em análise climatológica',
        'Outlier': 'Ponto de dados que se desvia significativamente do padrão normal'
    };

    document.querySelectorAll('.md-typeset p').forEach(paragraph => {
        let html = paragraph.innerHTML;
        
        Object.keys(technicalTerms).forEach(term => {
            const regex = new RegExp(`(^|\\s)(${term})(?=\\s|$|[.,;:!?])`, 'gi');
            html = html.replace(regex, 
                `$1<span class="custom-tooltip" data-tooltip="${technicalTerms[term]}">$2</span>`
            );
        });
        
        paragraph.innerHTML = html;
    });
}

// ========== INICIALIZAÇÃO FINAL ==========
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(() => {
        initScrollProgress();
        initTooltips();
        enhanceTables();
        enhanceSearch();
        showLoadingStates();
        
        console.log('✨ Todas as melhorias do Loczcit-IQR foram aplicadas');
    }, 500);
});

function initScrollProgress() {
    const progressBar = document.createElement('div');
    progressBar.className = 'scroll-progress';
    document.body.appendChild(progressBar);
    
    function updateScrollProgress() {
        const winScroll = document.body.scrollTop || document.documentElement.scrollTop;
        const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
        const scrolled = (winScroll / height) * 100;
        progressBar.style.width = scrolled + '%';
    }
    
    window.addEventListener('scroll', updateScrollProgress);
    updateScrollProgress();
}

function enhanceTables() {
    document.querySelectorAll('.md-typeset table').forEach(table => {
        table.classList.add('enhanced-table');
        
        const wrapper = document.createElement('div');
        wrapper.className = 'table-wrapper';
        wrapper.style.cssText = `
            overflow-x: auto;
            margin: var(--spacing-lg) 0;
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-md);
        `;
        
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);
        
        if (table.querySelectorAll('th').length > 0) {
            addTableSorting(table);
        }
    });
}

function addTableSorting(table) {
    const headers = table.querySelectorAll('th');
    headers.forEach((header, index) => {
        header.style.cursor = 'pointer';
        header.style.userSelect = 'none';
        header.addEventListener('click', () => sortTable(table, index));
        
        header.innerHTML += ' <span style="color: var(--text-tertiary); font-size: 0.8em;">⇅</span>';
    });
}

function sortTable(table, columnIndex) {
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const isNumeric = rows.every(row => {
        const cell = row.cells[columnIndex];
        return cell && !isNaN(parseFloat(cell.textContent.replace(/[^\d.-]/g, '')));
    });
    
    rows.sort((a, b) => {
        const aVal = a.cells[columnIndex].textContent.trim();
        const bVal = b.cells[columnIndex].textContent.trim();
        
        if (isNumeric) {
            return parseFloat(aVal.replace(/[^\d.-]/g, '')) - parseFloat(bVal.replace(/[^\d.-]/g, ''));
        } else {
            return aVal.localeCompare(bVal, 'pt-BR');
        }
    });
    
    const tbody = table.querySelector('tbody');
    rows.forEach(row => tbody.appendChild(row));
}

function enhanceSearch() {
    const searchInput = document.querySelector('.md-search__input');
    if (searchInput) {
        const suggestions = [
            'instalação', 'configuração', 'tutorial', 'API', 'exemplos',
            'ZCIT', 'IQR', 'climatologia', 'pentada', 'ROL',
            'análise', 'visualização', 'dados', 'metodologia'
        ];
        
        searchInput.addEventListener('input', function() {
            const value = this.value.toLowerCase();
            if (value.length > 1) {
                const matches = suggestions.filter(s => s.includes(value));
                showSearchSuggestions(matches, this);
            }
        });
    }
}

function showSearchSuggestions(suggestions, input) {
    const existingSuggestions = document.querySelector('.search-suggestions');
    if (existingSuggestions) {
        existingSuggestions.remove();
    }
    
    if (suggestions.length === 0) return;
    
    const suggestionBox = document.createElement('div');
    suggestionBox.className = 'search-suggestions';
    suggestionBox.style.cssText = `
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: var(--bg-primary);
        border: 1px solid var(--border-medium);
        border-radius: 0 0 var(--radius-lg) var(--radius-lg);
        box-shadow: var(--shadow-lg);
        z-index: 1000;
        max-height: 200px;
        overflow-y: auto;
    `;
    
    suggestions.slice(0, 5).forEach(suggestion => {
        const item = document.createElement('div');
        item.textContent = suggestion;
        item.style.cssText = `
            padding: var(--spacing-sm) var(--spacing-md);
            cursor: pointer;
            transition: background-color var(--transition-base);
        `;
        
        item.addEventListener('mouseenter', () => {
            item.style.backgroundColor = 'var(--bg-tertiary)';
        });
        
        item.addEventListener('mouseleave', () => {
            item.style.backgroundColor = '';
        });
        
        item.addEventListener('click', () => {
            input.value = suggestion;
            input.dispatchEvent(new Event('input'));
            suggestionBox.remove();
        });
        
        suggestionBox.appendChild(item);
    });
    
    input.parentNode.style.position = 'relative';
    input.parentNode.appendChild(suggestionBox);
    
    setTimeout(() => {
        document.addEventListener('click', function handler(e) {
            if (!input.parentNode.contains(e.target)) {
                suggestionBox.remove();
                document.removeEventListener('click', handler);
            }
        });
    }, 100);
}

function showLoadingStates() {
    document.querySelectorAll('img, iframe, video').forEach(element => {
        element.classList.add('loading');
        
        element.addEventListener('load', () => {
            element.classList.remove('loading');
        });
        
        element.addEventListener('error', () => {
            element.classList.remove('loading');
            element.style.opacity = '0.5';
        });
    });
}

console.log('🎯 Loczcit-IQR JavaScript carregado completamente!');