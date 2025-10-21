(function () {
    const stateNode = document.getElementById('mozello-catalog-state');
    if (!stateNode) {
        return;
    }

    let payload;
    try {
        payload = JSON.parse(stateNode.textContent || '{}');
    } catch (err) {
        console.warn('catalog payload parse error', err);
        return;
    }

    if (!payload || payload.mode !== 'non_admin') {
        return;
    }

    const purchased = new Set(Array.isArray(payload.purchased) ? payload.purchased.map(Number) : []);
    const mozelloBase = String(payload.mozello_base || '/mozello/books/');
    const buyLabel = String(payload.buy_label || 'Buy Online');
    const iconClass = String(payload.cart_icon_class || 'glyphicon-shopping-cart');
    let lastSelectedBookId = null;

    document.body.classList.add('catalog-non-admin');
    document.body.dataset.catalogMode = payload.mode;

    const normalizeBookId = (value) => {
        if (value === null || value === undefined) {
            return null;
        }
        const parsed = parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : null;
    };

    const hrefToBookId = (href) => {
        if (!href || typeof href !== 'string') {
            return null;
        }
        const match = href.match(/\/book\/(\d+)/);
        if (!match) {
            return null;
        }
        return normalizeBookId(match[1]);
    };

    const buildMozelloUrl = (bookId) => {
        if (bookId === null) {
            return null;
        }
        return mozelloBase.endsWith('/') ? `${mozelloBase}${bookId}` : `${mozelloBase}/${bookId}`;
    };

    const removeExistingBadge = (root) => {
        const badge = root.querySelector('.catalog-buy-badge');
        if (badge) {
            badge.remove();
        }
    };

    const ensureBuyBadge = (bookEl, bookId) => {
        if (!bookEl) {
            return;
        }
        if (purchased.has(bookId)) {
            bookEl.classList.add('book-purchased');
            removeExistingBadge(bookEl);
            return;
        }
        const cover = bookEl.querySelector('.cover');
        if (!cover || cover.querySelector('.catalog-buy-badge')) {
            return;
        }
        const mozelloUrl = buildMozelloUrl(bookId);
        if (!mozelloUrl) {
            return;
        }
        const badge = document.createElement('a');
        badge.className = 'catalog-buy-badge';
        badge.href = mozelloUrl;
        badge.title = buyLabel;
        badge.setAttribute('aria-label', buyLabel);
        badge.innerHTML = `<span class="glyphicon ${iconClass}"></span>`;
        cover.appendChild(badge);
        bookEl.classList.add('book-available');
    };

    const decorateGrid = () => {
        const cards = document.querySelectorAll('.book.session');
        cards.forEach((card) => {
            const anchor = card.querySelector('a[href*="/book/"]');
            const bookHref = anchor ? anchor.getAttribute('href') : null;
            const bookId = hrefToBookId(bookHref);
            if (!bookId) {
                return;
            }
            if (anchor) {
                anchor.addEventListener('click', () => {
                    lastSelectedBookId = bookId;
                });
            }
            ensureBuyBadge(card, bookId);
        });
    };

    const removeGroup = (root, selector) => {
        const node = root.querySelector(selector);
        if (!node) {
            return false;
        }
        const group = node.closest('.btn-group');
        if (group) {
            group.remove();
        } else {
            node.remove();
        }
        return true;
    };

    const injectBuyButton = (root, bookId) => {
        const toolbarGroup = root.querySelector('.btn-toolbar [role="group"][aria-label]');
        if (!toolbarGroup || toolbarGroup.querySelector('.catalog-buy-button')) {
            return;
        }
        const mozelloUrl = buildMozelloUrl(bookId);
        if (!mozelloUrl) {
            return;
        }
        const buyGroup = document.createElement('div');
        buyGroup.className = 'btn-group';
        const buyButton = document.createElement('a');
        buyButton.className = 'btn btn-primary catalog-buy-button';
        buyButton.href = mozelloUrl;
        buyButton.innerHTML = `<span class="glyphicon ${iconClass}"></span> ${buyLabel}`;
        buyGroup.appendChild(buyButton);
        toolbarGroup.appendChild(buyGroup);
    };

    const hideIdentifiers = (root) => {
        root.querySelectorAll('.identifiers').forEach((node) => {
            node.style.display = 'none';
        });
    };

    const applyDetailTransform = (root, bookId) => {
        hideIdentifiers(root);
        if (!bookId) {
            return;
        }
        if (purchased.has(bookId)) {
            return;
        }
        removeGroup(root, '#readbtn');
        removeGroup(root, '#read-in-browser');
        removeGroup(root, '#listenbtn');
        removeGroup(root, '#listen-in-browser');
        injectBuyButton(root, bookId);
    };

    const decorateDetailPage = () => {
        const pathMatch = window.location.pathname.match(/\/book\/(\d+)/);
        const bookId = normalizeBookId(pathMatch ? pathMatch[1] : null);
        if (!bookId) {
            hideIdentifiers(document);
            return;
        }
        applyDetailTransform(document, bookId);
    };

    const decorateDetailModal = () => {
        const modal = document.getElementById('bookDetailsModal');
        if (!modal) {
            return;
        }

        const resolveBookIdFromModal = () => {
            if (lastSelectedBookId) {
                return lastSelectedBookId;
            }
            const readLink = modal.querySelector('a[href*="/read/"]');
            if (readLink) {
                const match = readLink.getAttribute('href').match(/\/read\/(\d+)\//);
                if (match) {
                    return normalizeBookId(match[1]);
                }
            }
            const button = modal.querySelector('[data-book-id]');
            if (button) {
                return normalizeBookId(button.getAttribute('data-book-id'));
            }
            const titleLink = modal.querySelector('a[href*="/book/"]');
            if (titleLink) {
                return hrefToBookId(titleLink.getAttribute('href'));
            }
            return null;
        };

        const handleModalShown = () => {
            const bookId = resolveBookIdFromModal();
            applyDetailTransform(modal, bookId);
        };

        const handleModalHidden = () => {
            lastSelectedBookId = null;
        };

        const bindBootstrapEvent = (name, handler) => {
            const jq = window.jQuery;
            if (jq && typeof jq === 'function' && jq.fn && typeof jq.fn.on === 'function') {
                jq(modal).on(name, handler);
            } else {
                modal.addEventListener(name, handler, false);
            }
        };

        bindBootstrapEvent('shown.bs.modal', handleModalShown);
        bindBootstrapEvent('loaded.bs.modal', handleModalShown);
        bindBootstrapEvent('hidden.bs.modal', handleModalHidden);

        const modalBody = modal.querySelector('.modal-body');
        if (modalBody && typeof MutationObserver === 'function') {
            const observer = new MutationObserver(() => {
                if (!modal.classList.contains('in')) {
                    return;
                }
                handleModalShown();
            });
            observer.observe(modalBody, { childList: true, subtree: true });
        }
    };

    hideIdentifiers(document);
    decorateGrid();
    decorateDetailPage();
    decorateDetailModal();
})();
