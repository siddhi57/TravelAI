/* TravelAI Companion Client-Side Javascript */

document.addEventListener('DOMContentLoaded', function () {
    // Auto-dismiss Bootstrap flash alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // AJAX Like Toggle for Community Feed
    const likeButtons = document.querySelectorAll('.btn-like');
    likeButtons.forEach(button => {
        button.addEventListener('click', function (e) {
            e.preventDefault();
            const postId = this.getAttribute('data-post-id');
            const likeIcon = this.querySelector('i');
            const countSpan = this.querySelector('.like-count');

            fetch(`/community/like/${postId}`, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/json'
                }
            })
            .then(response => {
                if (response.redirected) {
                    window.location.href = response.url;
                    return;
                }
                return response.json();
            })
            .then(data => {
                if (data) {
                    countSpan.textContent = data.likes_count;
                    if (data.liked) {
                        likeIcon.classList.remove('bi-heart');
                        likeIcon.classList.add('bi-heart-fill', 'text-danger');
                        this.classList.add('btn-light-danger');
                    } else {
                        likeIcon.classList.remove('bi-heart-fill', 'text-danger');
                        likeIcon.classList.add('bi-heart');
                        this.classList.remove('btn-light-danger');
                    }
                }
            })
            .catch(err => console.error('Error toggling like:', err));
        });
    });
});

/**
 * Helper to initialize OpenStreetMap Leaflet map with pins
 * @param {string} mapId - ID of DOM element
 * @param {number} centerLat 
 * @param {number} centerLng 
 * @param {number} zoomLevel 
 * @param {Array} markers - Array of objects: {lat, lng, title, description, category}
 */
function initLeafletMap(mapId, centerLat, centerLng, zoomLevel = 12, markers = []) {
    const mapElement = document.getElementById(mapId);
    if (!mapElement) return null;

    const map = L.map(mapId).setView([centerLat, centerLng], zoomLevel);

    // OpenStreetMap Tile Layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    // Custom icon colors based on category
    const defaultIcon = L.icon({
        iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
    });

    if (markers && markers.length > 0) {
        const bounds = [];
        markers.forEach(m => {
            if (m.lat && m.lng) {
                const marker = L.marker([m.lat, m.lng], { icon: defaultIcon }).addTo(map);
                const popupContent = `
                    <div style="font-size:14px; max-width:200px;">
                        <strong>${m.title || 'Location'}</strong><br/>
                        ${m.category ? `<span class="badge bg-secondary mb-1">${m.category}</span><br/>` : ''}
                        <small>${m.description || m.address || ''}</small>
                    </div>
                `;
                marker.bindPopup(popupContent);
                bounds.push([m.lat, m.lng]);
            }
        });

        if (bounds.length > 1) {
            map.fitBounds(bounds, { padding: [30, 30] });
        }
    }

    return map;
}
