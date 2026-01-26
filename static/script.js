// Global variables
let sessionId = generateSessionId();
let isWaitingForResponse = false;
let currentMap = null;
let currentChart = null;

// DOM elements
const messagesArea = document.getElementById('messagesArea');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const typingIndicator = document.getElementById('typingIndicator');
const contactModal = document.getElementById('contactModal');
const contactForm = document.getElementById('contactForm');
const quickButtons = document.querySelectorAll('.quick-btn');

// Initialize
document.addEventListener('DOMContentLoaded', function () {
    console.log('🚀 Script.js loaded - Version 20250122');
    setupEventListeners();
    messageInput.focus();
});

// Event listeners
function setupEventListeners() {
    // Send message on button click
    sendButton.addEventListener('click', sendMessage);

    // Send message on Enter key
    messageInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Quick action buttons
    quickButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            const message = this.getAttribute('data-message');
            messageInput.value = message;
            sendMessage();
        });
    });

    // Contact modal
    document.getElementById('closeModal').addEventListener('click', closeContactModal);
    document.getElementById('cancelContact').addEventListener('click', closeContactModal);
    contactForm.addEventListener('submit', submitContact);

    // Close modal on outside click
    contactModal.addEventListener('click', function (e) {
        if (e.target === contactModal) {
            closeContactModal();
        }
    });
}

// Generate session ID
function generateSessionId() {
    return 'session-' + Math.random().toString(36).substring(2, 11) + '-' + Date.now();
}

// Send message
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message || isWaitingForResponse) return;

    // Add user message to chat
    addMessage(message, 'user');
    messageInput.value = '';

    // Show typing indicator
    showTypingIndicator();
    isWaitingForResponse = true;
    sendButton.disabled = true;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-Id': sessionId
            },
            body: JSON.stringify({
                question: message,
                session_id: sessionId
            })
        });

        const data = await response.json();

        // Hide typing indicator
        hideTypingIndicator();

        if (response.ok) {
            handleBotResponse(data, message);
        } else {
            addMessage('Xin lỗi, đã có lỗi xảy ra: ' + (data.detail || 'Lỗi không xác định'), 'bot');
        }
    } catch (error) {
        hideTypingIndicator();
        addMessage('Xin lỗi, không thể kết nối đến server. Vui lòng thử lại sau.', 'bot');
        console.error('Error:', error);
    } finally {
        isWaitingForResponse = false;
        sendButton.disabled = false;
        messageInput.focus();
    }
}

// Handle bot response
function handleBotResponse(data, originalMessage) {
    console.log('🤖 handleBotResponse được gọi với data:', data);
    console.log('🔍 Response type:', data.type);
    console.log('📝 Response answer:', data.answer);

    if (data.requires_contact) {
        showContactModal(originalMessage);
        return;
    }

    // Handle different response types
    switch (data.type) {
        case 'excel_query':
            handleExcelResponse(data.answer, data.map_intent);
            break;
        case 'flowchart':
            handleFlowchartResponse(data.payload);
            break;
        case 'excel_visualize':
            handleVisualizationResponse(data.payload);
            break;
        case 'kcn_detail':
            console.log('🏭 CASE KCN_DETAIL được kích hoạt!');
            console.log('🏭 data.answer:', data.answer);
            console.log('🏭 typeof data.answer:', typeof data.answer);
            console.log('🏭 Gọi handleKCNDetailResponse với:', data.answer);
            handleKCNDetailResponse(data.answer);
            break;
        default:
            console.log('📝 Default case - hiển thị answer trực tiếp:', data.answer);
            // Kiểm tra nếu answer là object thì convert sang JSON string hoặc hiển thị lỗi
            if (typeof data.answer === 'object' && data.answer !== null) {
                console.warn('⚠️ Answer là object trong default case:', data.answer);

                // Nếu là KCN object nhưng type không đúng, thử xử lý như KCN
                if (data.answer.kcn_info && data.answer.coordinates) {
                    console.log('🔄 Phát hiện KCN object, chuyển sang handleKCNDetailResponse');
                    handleKCNDetailResponse(data.answer);
                } else {
                    // Object khác, hiển thị thông báo lỗi thân thiện
                    addMessage('Xin lỗi, có lỗi trong việc hiển thị kết quả. Vui lòng thử lại.', 'bot');
                }
            } else {
                // String bình thường
                addMessage(data.answer, 'bot');
            }
    }
}

// Handle Excel query response
function handleExcelResponse(answer, mapIntent) {
    console.log('🔍 handleExcelResponse được gọi');
    console.log('answer:', answer);
    console.log('mapIntent:', mapIntent);

    if (typeof answer === 'object') {
        if (answer.error) {
            addMessage(answer.error, 'bot');
            return;
        }

        let responseText = '';
        if (answer.message) {
            responseText += answer.message + '\n\n';
        }

        if (answer.data && answer.data.length > 0) {
            console.log('📊 Có data, tạo dataView...');
            // Create enhanced data view with map and table
            const dataViewHtml = createDataView(answer, mapIntent);
            console.log('📝 HTML được tạo:', dataViewHtml.substring(0, 200) + '...');
            addMessage(responseText + dataViewHtml, 'bot', true);

            // Initialize map if coordinates available
            if (mapIntent && mapIntent.iz_list && mapIntent.iz_list.length > 0) {
                console.log('🗺️ Khởi tạo bản đồ sau 500ms...');
                setTimeout(() => initializeMap(mapIntent), 500);
            } else {
                console.log('❌ Không có mapIntent hoặc iz_list');
            }
        } else {
            console.log('❌ Không có data');
            addMessage(responseText || 'Không tìm thấy kết quả phù hợp.', 'bot');
        }
    } else {
        console.log('📝 Answer là string, hiển thị trực tiếp');
        addMessage(answer, 'bot');
    }
}

// Create enhanced data view
function createDataView(answer, mapIntent) {
    const hasCoordinates = mapIntent && mapIntent.iz_list && mapIntent.iz_list.length > 0;
    const mapId = 'map-' + Date.now();

    console.log('createDataView được gọi');
    console.log('hasCoordinates:', hasCoordinates);
    console.log('mapIntent:', mapIntent);
    console.log('mapId:', mapId);

    let html = '<div class="data-view-container">';

    // Header with view toggle and export button
    html += '<div class="data-view-header">';
    html += `<div class="data-view-title">📊 ${answer.message || 'Kết quả tìm kiếm'}</div>`;
    html += '<div class="header-controls">';

    // Export JSON button
    html += '<div class="export-controls">';
    html += `<button class="export-btn" onclick="exportToJSON('${answer.province || 'Unknown'}', '${answer.type || 'KCN'}')">`;
    html += '<i class="fas fa-download"></i> Xuất JSON</button>';
    html += '</div>';

    // View toggle buttons
    html += '<div class="view-toggle">';
    if (hasCoordinates) {
        html += '<button class="view-btn active" onclick="switchView(this, \'map\')"><i class="fas fa-map"></i> Bản đồ</button>';
    }
    html += '<button class="view-btn' + (!hasCoordinates ? ' active' : '') + '" onclick="switchView(this, \'table\')"><i class="fas fa-table"></i> Bảng</button>';
    html += '<button class="view-btn" onclick="switchView(this, \'grid\')"><i class="fas fa-th"></i> Thẻ</button>';
    html += '</div>';
    html += '</div></div>';

    // Content area
    html += '<div class="data-content">';

    // Map view
    if (hasCoordinates) {
        console.log('Tạo HTML cho bản đồ với mapId:', mapId);
        html += `<div class="view-content map-view active">`;
        html += '<div class="map-container">';
        html += '<div class="map-header">';
        html += '<div class="map-title"><i class="fas fa-map-marker-alt"></i>Bản đồ khu công nghiệp</div>';
        html += '<div class="map-controls">';
        html += '<button class="map-btn" onclick="toggleMapLayer(\'satellite\')"><i class="fas fa-satellite"></i> Vệ tinh</button>';
        html += '<button class="map-btn active" onclick="toggleMapLayer(\'street\')"><i class="fas fa-road"></i> Đường phố</button>';
        html += '</div></div>';
        html += `<div id="${mapId}" class="map-view-container" style="height: 500px; border-radius: 8px; background: #f0f0f0; display: flex; align-items: center; justify-content: center; color: #666;">Đang tải bản đồ...</div>`;
        html += `<div class="map-info">• Click vào cụm để zoom • Click vào điểm để xem chi tiết • Tổng: ${answer.count || mapIntent.iz_list.length} điểm</div>`;
        html += '</div></div>';
    } else {
        console.log('Không có tọa độ, bỏ qua bản đồ');
    }

    // Table view
    html += `<div class="view-content table-view${!hasCoordinates ? ' active' : ''}">`;
    html += createTableView(answer.data);
    html += '</div>';

    // Grid view
    html += '<div class="view-content grid-view">';
    html += createGridView(answer.data);
    html += '</div>';

    html += '</div></div>';

    // Store map data for initialization
    if (hasCoordinates) {
        console.log('Lưu pendingMapData cho mapId:', mapId);
        window.pendingMapData = { mapId, mapIntent };
    }

    return html;
}

// Create table view
function createTableView(data) {
    let html = '<div class="table-view"><table class="excel-table">';
    html += '<thead><tr>';
    html += '<th>#</th><th>Tên</th><th>Địa chỉ</th><th>Diện tích</th><th>Giá thuê</th><th>Ngành nghề</th>';
    html += '</tr></thead><tbody>';

    data.slice(0, 20).forEach((item, index) => {
        html += '<tr>';
        html += `<td>${index + 1}</td>`;
        html += `<td><strong>${item['Tên'] || 'N/A'}</strong></td>`;
        html += `<td>${item['Địa chỉ'] || 'N/A'}</td>`;
        html += `<td>${item['Tổng diện tích'] || 'N/A'}</td>`;
        html += `<td>${item['Giá thuê đất'] || 'N/A'}</td>`;
        html += `<td>${(item['Ngành nghề'] || 'N/A').substring(0, 100)}${item['Ngành nghề'] && item['Ngành nghề'].length > 100 ? '...' : ''}</td>`;
        html += '</tr>';
    });

    html += '</tbody></table>';
    if (data.length > 20) {
        html += `<p style="text-align: center; margin-top: 1rem; color: #6c757d;"><em>Hiển thị 20/${data.length} kết quả đầu tiên</em></p>`;
    }
    html += '</div>';

    return html;
}

// Create grid view
function createGridView(data) {
    let html = '<div class="grid-view">';

    data.slice(0, 12).forEach((item, index) => {
        html += '<div class="grid-item">';
        html += `<h5>${item['Tên'] || 'N/A'}</h5>`;
        html += `<p><i class="fas fa-map-marker-alt"></i> ${item['Địa chỉ'] || 'N/A'}</p>`;
        html += `<p><i class="fas fa-expand-arrows-alt"></i> Diện tích: <span class="highlight">${item['Tổng diện tích'] || 'N/A'}</span></p>`;
        html += `<p><i class="fas fa-dollar-sign"></i> Giá thuê: <span class="highlight">${item['Giá thuê đất'] || 'N/A'}</span></p>`;
        if (item['Thời gian vận hành']) {
            html += `<p><i class="fas fa-clock"></i> Vận hành: ${item['Thời gian vận hành']}</p>`;
        }
        html += '</div>';
    });

    html += '</div>';
    if (data.length > 12) {
        html += `<p style="text-align: center; margin-top: 1rem; color: #6c757d;"><em>Hiển thị 12/${data.length} kết quả đầu tiên</em></p>`;
    }

    return html;
}

// Switch between views
function switchView(button, viewType) {
    const container = button.closest('.data-view-container');
    const viewButtons = container.querySelectorAll('.view-btn');
    const viewContents = container.querySelectorAll('.view-content');

    // Update button states
    viewButtons.forEach(btn => btn.classList.remove('active'));
    button.classList.add('active');

    // Update content visibility
    viewContents.forEach(content => content.classList.remove('active'));
    const targetView = container.querySelector(`.${viewType}-view`);
    if (targetView) {
        targetView.classList.add('active');

        // Initialize map if switching to map view
        if (viewType === 'map' && window.pendingMapData) {
            setTimeout(() => initializeMap(window.pendingMapData.mapIntent, window.pendingMapData.mapId), 100);
        }
    }
}

// Initialize map - Sử dụng Leaflet với Province Zoom
function initializeMap(mapIntent, mapId = null) {
    if (!mapId && window.pendingMapData) {
        mapId = window.pendingMapData.mapId;
    }

    if (!mapId) {
        console.error('Không có mapId để khởi tạo bản đồ');
        return;
    }

    const mapContainer = document.getElementById(mapId);
    if (!mapContainer) {
        console.error('Không tìm thấy container bản đồ:', mapId);
        return;
    }

    if (!mapIntent || !mapIntent.iz_list) {
        console.error('Không có dữ liệu mapIntent hoặc iz_list');
        return;
    }

    console.log('Khởi tạo bản đồ với', mapIntent.iz_list.length, 'điểm');

    // Destroy existing map
    if (currentMap) {
        if (currentMap.remove) {
            currentMap.remove();
        }
        currentMap = null;
    }

    try {
        // Sử dụng Leaflet
        if (typeof L === 'undefined') {
            console.error('Leaflet chưa được tải');
            mapContainer.innerHTML = '<div style="padding: 20px; text-align: center; color: #e74c3c;">Lỗi: Không thể tải thư viện bản đồ</div>';
            return;
        }

        console.log('Khởi tạo Leaflet map...');

        // Tạo bản đồ Leaflet
        currentMap = L.map(mapId).setView([21.0285, 105.8542], 7);

        // Thêm tile layer OpenStreetMap
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(currentMap);

        const group = new L.featureGroup();
        let markerCount = 0;

        // Thêm markers
        mapIntent.iz_list.forEach(item => {
            if (item.coordinates && item.coordinates.length === 2) {
                const [lng, lat] = item.coordinates;

                if (isNaN(lng) || isNaN(lat)) {
                    console.warn('Tọa độ không hợp lệ:', item.coordinates);
                    return;
                }

                const popupContent = `
                    <div style="min-width: 200px; font-family: Arial, sans-serif;">
                        <h4 style="margin: 0 0 0.5rem 0; color: #2c3e50; font-size: 14px;">${item.name || 'Không có tên'}</h4>
                        <p style="margin: 0.2rem 0; font-size: 12px;">📍 ${item.address || 'Không có địa chỉ'}</p>
                        <p style="margin: 0.2rem 0; font-size: 12px;">🏭 ${item.kind || 'KCN'}</p>
                    </div>
                `;

                const marker = L.marker([lat, lng])
                    .bindPopup(popupContent)
                    .addTo(currentMap);

                // Thêm marker vào group để tính bounds
                group.addLayer(marker);
                markerCount++;
            }
        });

        console.log('Đã thêm', markerCount, 'marker vào bản đồ');

        // 🎯 PROVINCE ZOOM INTEGRATION - Ưu tiên province zoom từ backend
        if (mapIntent.province_zoom) {
            console.log('🎯 Áp dụng province zoom từ backend:', mapIntent.province_zoom);

            const { bounds: provinceBounds, center, zoom_level } = mapIntent.province_zoom;

            if (provinceBounds && provinceBounds.length === 4) {
                const [minLng, minLat, maxLng, maxLat] = provinceBounds;

                // Tạo bounds từ province data cho Leaflet
                const leafletBounds = L.latLngBounds(
                    L.latLng(minLat, minLng), // southwest
                    L.latLng(maxLat, maxLng)  // northeast
                );

                // 🎯 ZOOM THÔNG MINH: Nếu có ít markers, zoom vào markers thay vì province
                if (markerCount <= 3 && markerCount > 0) {
                    // Ít markers: zoom vào markers với padding nhỏ hơn và zoom cao hơn
                    currentMap.fitBounds(group.getBounds(), {
                        padding: [10, 10],
                        maxZoom: Math.min(zoom_level + 2, 16)  // Zoom cao hơn 2 level
                    });
                    console.log('✅ Đã zoom vào markers (ít điểm, zoom cao)');
                } else {
                    // Nhiều markers: zoom vào province bounds
                    currentMap.fitBounds(leafletBounds, {
                        padding: [20, 20],
                        maxZoom: zoom_level || 15  // Tăng maxZoom từ 12 lên 15
                    });
                    console.log('✅ Đã zoom vào tỉnh:', mapIntent.province_zoom.province_name);
                }
            }
        } else if (markerCount > 0) {
            // Fallback: Zoom vào vùng chứa tất cả markers nếu không có province zoom
            currentMap.fitBounds(group.getBounds(), {
                padding: [20, 20],
                maxZoom: 15  // Tăng maxZoom
            });
            console.log('✅ Đã zoom vào vùng chứa markers');
        }

        console.log('✅ Bản đồ Leaflet đã tải thành công');

    } catch (error) {
        console.error('Lỗi khởi tạo bản đồ:', error);
        mapContainer.innerHTML = '<div style="padding: 20px; text-align: center; color: #e74c3c;">Lỗi khởi tạo bản đồ: ' + error.message + '</div>';
    }
}

// Toggle map layer - Cập nhật cho Leaflet
function toggleMapLayer(layerType) {
    if (!currentMap) return;

    // Xóa tất cả tile layers hiện tại
    currentMap.eachLayer(function (layer) {
        if (layer instanceof L.TileLayer) {
            currentMap.removeLayer(layer);
        }
    });

    // Thêm tile layer mới
    let tileLayer;
    switch (layerType) {
        case 'satellite':
            tileLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
                attribution: '© Esri'
            });
            break;
        case 'street':
        default:
            tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            });
            break;
    }

    tileLayer.addTo(currentMap);

    // Update button states
    document.querySelectorAll('.map-btn').forEach(btn => btn.classList.remove('active'));
    const clickedButton = document.querySelector(`[onclick*="${layerType}"]`);
    if (clickedButton) {
        clickedButton.classList.add('active');
    }
}

// Handle KCN Detail response
function handleKCNDetailResponse(kcnData) {
    console.log('🏭 handleKCNDetailResponse được gọi:', kcnData);

    // Validation: Đảm bảo kcnData là object và có đủ thông tin
    if (!kcnData || typeof kcnData !== 'object') {
        console.error('❌ KCN Data không hợp lệ:', kcnData);
        addMessage('Lỗi: Dữ liệu KCN không hợp lệ', 'bot');
        return;
    }

    const kcnInfo = kcnData.kcn_info;
    const coordinates = kcnData.coordinates;
    const zoomLevel = kcnData.zoom_level || 16;

    // Validation: Đảm bảo có thông tin KCN
    if (!kcnInfo || typeof kcnInfo !== 'object') {
        console.error('❌ KCN Info không hợp lệ:', kcnInfo);
        addMessage('Lỗi: Thông tin KCN không đầy đủ', 'bot');
        return;
    }

    // Tạo HTML hiển thị thông tin chi tiết KCN
    let responseHtml = '<div class="kcn-detail-container">';

    // Header
    responseHtml += '<div class="kcn-detail-header">';
    responseHtml += `<h4>🏭 ${kcnInfo['Tên'] || 'Khu công nghiệp'}</h4>`;
    responseHtml += `<div class="kcn-match-info">Độ chính xác: ${kcnData.match_score || 'N/A'}%</div>`;
    responseHtml += '</div>';

    // Thông tin cơ bản
    responseHtml += '<div class="kcn-basic-info">';
    responseHtml += '<div class="info-grid">';

    if (kcnInfo['Địa chỉ']) {
        responseHtml += `<div class="info-item"><strong>📍 Địa chỉ:</strong> ${kcnInfo['Địa chỉ']}</div>`;
    }
    if (kcnInfo['Tỉnh/Thành phố']) {
        responseHtml += `<div class="info-item"><strong>🗺️ Tỉnh/Thành phố:</strong> ${kcnInfo['Tỉnh/Thành phố']}</div>`;
    }
    if (kcnInfo['Loại']) {
        responseHtml += `<div class="info-item"><strong>🏷️ Loại:</strong> ${kcnInfo['Loại']}</div>`;
    }
    if (kcnInfo['Tổng diện tích']) {
        responseHtml += `<div class="info-item"><strong>📐 Diện tích:</strong> ${kcnInfo['Tổng diện tích']}</div>`;
    }
    if (kcnInfo['Giá thuê đất']) {
        responseHtml += `<div class="info-item"><strong>💰 Giá thuê:</strong> ${kcnInfo['Giá thuê đất']}</div>`;
    }
    if (kcnInfo['Thời gian vận hành']) {
        responseHtml += `<div class="info-item"><strong>⏰ Thời gian vận hành:</strong> ${kcnInfo['Thời gian vận hành']}</div>`;
    }

    responseHtml += '</div></div>';

    // RAG Analysis Section - Hiển thị phân tích từ RAG nếu có
    if (kcnData.rag_analysis && kcnData.has_rag) {
        responseHtml += '<div class="kcn-rag-analysis">';
        responseHtml += '<h5>🤖 Phân tích chi tiết từ AI:</h5>';
        responseHtml += '<div class="rag-analysis-content">';
        responseHtml += kcnData.rag_analysis.replace(/\n/g, '<br>');
        responseHtml += '</div>';
        responseHtml += '<div class="rag-badge">✨ Được tăng cường bởi RAG AI</div>';
        responseHtml += '</div>';
    }

    // Ngành nghề
    if (kcnInfo['Ngành nghề']) {
        responseHtml += '<div class="kcn-industries">';
        responseHtml += '<h5>🏭 Ngành nghề được phép:</h5>';
        responseHtml += `<div class="industries-content">${kcnInfo['Ngành nghề']}</div>`;
        responseHtml += '</div>';
    }

    // Hạ tầng
    responseHtml += '<div class="kcn-infrastructure">';
    responseHtml += '<h5>🔧 Hạ tầng:</h5>';
    responseHtml += '<div class="infrastructure-grid">';

    if (kcnInfo['Hệ thống cấp điện']) {
        responseHtml += `<div class="infra-item"><strong>⚡ Điện:</strong> ${kcnInfo['Hệ thống cấp điện']}</div>`;
    }
    if (kcnInfo['Hệ thống cấp nước']) {
        responseHtml += `<div class="infra-item"><strong>💧 Nước:</strong> ${kcnInfo['Hệ thống cấp nước']}</div>`;
    }
    if (kcnInfo['Hệ thống xử lý nước thải']) {
        responseHtml += `<div class="infra-item"><strong>🚰 Xử lý nước thải:</strong> ${kcnInfo['Hệ thống xử lý nước thải']}</div>`;
    }

    responseHtml += '</div></div>';

    // Ưu đãi
    if (kcnInfo['Ưu đãi']) {
        responseHtml += '<div class="kcn-incentives">';
        responseHtml += '<h5>🎁 Ưu đãi đầu tư:</h5>';
        responseHtml += `<div class="incentives-content">${kcnInfo['Ưu đãi']}</div>`;
        responseHtml += '</div>';
    }

    // Liên hệ
    if (kcnInfo['Liên hệ'] || kcnInfo['URL']) {
        responseHtml += '<div class="kcn-contact">';
        responseHtml += '<h5>📞 Thông tin liên hệ:</h5>';
        if (kcnInfo['Liên hệ']) {
            responseHtml += `<div class="contact-info">${kcnInfo['Liên hệ']}</div>`;
        }
        if (kcnInfo['URL']) {
            responseHtml += `<div class="contact-url"><a href="${kcnInfo['URL']}" target="_blank">🔗 Xem chi tiết</a></div>`;
        }
        responseHtml += '</div>';
    }

    // Bản đồ
    if (coordinates && Array.isArray(coordinates) && coordinates.length === 2) {
        const mapId = 'kcn-detail-map-' + Date.now();
        responseHtml += '<div class="kcn-map-section">';
        responseHtml += '<h5>🗺️ Vị trí trên bản đồ:</h5>';
        responseHtml += '<div class="map-container">';
        responseHtml += `<div id="${mapId}" class="kcn-detail-map" style="height: 400px; border-radius: 8px;"></div>`;
        responseHtml += `<div class="map-info">📍 Tọa độ: ${coordinates[1].toFixed(6)}, ${coordinates[0].toFixed(6)} | 🎯 Zoom: ${zoomLevel}</div>`;
        responseHtml += '</div></div>';

        // Lưu thông tin để khởi tạo bản đồ
        window.kcnDetailMapData = {
            mapId: mapId,
            coordinates: coordinates,
            zoomLevel: zoomLevel,
            name: kcnInfo['Tên'] || 'KCN',
            address: kcnInfo['Địa chỉ'] || ''
        };
    } else {
        console.warn('⚠️ Không có tọa độ hợp lệ cho KCN:', coordinates);
    }

    responseHtml += '</div>';

    // Hiển thị response với HTML
    addMessage(responseHtml, 'bot', true);

    // Khởi tạo bản đồ sau khi DOM được render
    if (coordinates && Array.isArray(coordinates) && coordinates.length === 2) {
        setTimeout(() => initializeKCNDetailMap(), 500);
    }
}

// Initialize KCN Detail Map
function initializeKCNDetailMap() {
    if (!window.kcnDetailMapData) {
        console.error('Không có dữ liệu bản đồ KCN');
        return;
    }

    const { mapId, coordinates, zoomLevel, name, address } = window.kcnDetailMapData;
    const mapContainer = document.getElementById(mapId);

    if (!mapContainer) {
        console.error('Không tìm thấy container bản đồ:', mapId);
        return;
    }

    if (typeof L === 'undefined') {
        console.error('Leaflet chưa được tải');
        mapContainer.innerHTML = '<div style="padding: 20px; text-align: center; color: #e74c3c;">Lỗi: Không thể tải thư viện bản đồ</div>';
        return;
    }

    console.log('🗺️ Khởi tạo bản đồ KCN chi tiết:', name, coordinates, zoomLevel);

    try {
        // Tạo bản đồ Leaflet với zoom chính xác
        const map = L.map(mapId).setView([coordinates[1], coordinates[0]], zoomLevel);

        // Thêm tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);

        // Tạo popup content
        const popupContent = `
            <div style="min-width: 250px; font-family: Arial, sans-serif;">
                <h4 style="margin: 0 0 0.5rem 0; color: #2c3e50; font-size: 16px;">${name}</h4>
                <p style="margin: 0.2rem 0; font-size: 13px;">📍 ${address}</p>
                <p style="margin: 0.2rem 0; font-size: 12px; color: #666;">🎯 Tọa độ: ${coordinates[1].toFixed(6)}, ${coordinates[0].toFixed(6)}</p>
            </div>
        `;

        // Thêm marker với popup
        const marker = L.marker([coordinates[1], coordinates[0]])
            .bindPopup(popupContent)
            .addTo(map);

        // Mở popup ngay lập tức
        marker.openPopup();

        console.log('✅ Bản đồ KCN chi tiết đã tải thành công');

    } catch (error) {
        console.error('Lỗi khởi tạo bản đồ KCN:', error);
        mapContainer.innerHTML = '<div style="padding: 20px; text-align: center; color: #e74c3c;">Lỗi khởi tạo bản đồ: ' + error.message + '</div>';
    }
}

// Handle flowchart response
function handleFlowchartResponse(payload) {
    let responseHtml = '<div class="flowchart-container">';
    responseHtml += '<h4>📊 Flowchart được tạo</h4>';

    if (payload.explanation) {
        responseHtml += `<p>${payload.explanation}</p>`;
    }

    if (payload.code) {
        responseHtml += '<pre style="background: #f8f9fa; padding: 1rem; border-radius: 5px; overflow-x: auto; text-align: left;">';
        responseHtml += payload.code;
        responseHtml += '</pre>';
    }

    responseHtml += '</div>';
    addMessage(responseHtml, 'bot', true);
}

// Handle visualization response
function handleVisualizationResponse(payload) {
    if (payload.type === 'error') {
        addMessage(`❌ Lỗi tạo biểu đồ: ${payload.message}`, 'bot');
        return;
    }

    // Nếu có cả chart và data (type: excel_visualize_with_data)
    if (payload.type === 'excel_visualize_with_data' && payload.data) {
        // Tạo map_intent từ data với province zoom
        const mapIntent = {
            type: "province",
            province: payload.province,
            iz_list: payload.data.filter(item => item.coordinates).map(item => ({
                name: item['Tên'],
                kind: item['Loại'],
                address: item['Địa chỉ'],
                coordinates: item.coordinates
            })),
            kind: payload.industrial_type,
            // 🎯 Thêm province zoom từ payload
            province_zoom: payload.province_zoom || null
        };

        // Hiển thị như excel query với cả biểu đồ
        let responseText = payload.message + '\n\n';

        // Tạo data view với biểu đồ
        const dataViewHtml = createDataViewWithChart(payload, mapIntent);
        addMessage(responseText + dataViewHtml, 'bot', true);

        // Initialize map if coordinates available
        if (mapIntent.iz_list && mapIntent.iz_list.length > 0) {
            setTimeout(() => initializeMap(mapIntent), 500);
        }
        return;
    }

    // Kiểm tra nếu có chart_base64 (biểu đồ thực)
    if (payload.chart_base64) {
        let responseHtml = '<div class="chart-result-container">';
        responseHtml += '<div class="chart-header">';
        responseHtml += '<h4>📊 ' + (payload.text || 'Biểu đồ được tạo') + '</h4>';
        responseHtml += '</div>';
        responseHtml += '<div class="chart-image-container">';
        responseHtml += `<img src="data:image/png;base64,${payload.chart_base64}" alt="Biểu đồ" style="max-width: 100%; height: auto; border-radius: 8px;">`;
        responseHtml += '</div>';

        // Hiển thị data nếu có
        if (payload.items && payload.items.length > 0) {
            responseHtml += '<div class="chart-data-summary">';
            responseHtml += `<p><strong>Tổng số:</strong> ${payload.items.length} ${payload.industrial_type || 'khu vực'}</p>`;
            responseHtml += `<p><strong>Khu vực:</strong> ${payload.province || 'Toàn quốc'}</p>`;
            responseHtml += '</div>';
        }

        responseHtml += '</div>';
        addMessage(responseHtml, 'bot', true);
    } else {
        // Fallback - chỉ hiển thị thông báo
        let responseHtml = '<div class="chart-success-container">';
        responseHtml += '<div class="chart-success-icon">📊</div>';
        responseHtml += '<div class="chart-success-text">';
        responseHtml += '<h4>Biểu đồ được tạo</h4>';
        responseHtml += '<p>Biểu đồ đã được tạo thành công!</p>';
        responseHtml += '</div>';
        responseHtml += '</div>';
        addMessage(responseHtml, 'bot', true);
    }
}

// Create data view with chart
function createDataViewWithChart(payload, mapIntent) {
    const hasCoordinates = mapIntent && mapIntent.iz_list && mapIntent.iz_list.length > 0;
    const mapId = 'map-' + Date.now();

    let html = '<div class="data-view-container">';

    // Chart section first
    if (payload.chart_base64) {
        html += '<div class="chart-section">';
        html += '<div class="chart-image-container">';
        html += `<img src="data:image/png;base64,${payload.chart_base64}" alt="Biểu đồ" style="max-width: 100%; height: auto; border-radius: 8px; margin-bottom: 1rem;">`;
        html += '</div>';
        html += '</div>';
    }

    // Header with view toggle and export button
    html += '<div class="data-view-header">';
    html += `<div class="data-view-title">📊 ${payload.message || 'Kết quả phân tích'}</div>`;
    html += '<div class="header-controls">';

    // Export JSON button
    html += '<div class="export-controls">';
    html += `<button class="export-btn" onclick="exportChartToJSON('${payload.province || 'Unknown'}', '${payload.industrial_type || 'KCN'}', '${payload.metric || 'chart'}')">`;
    html += '<i class="fas fa-download"></i> Xuất JSON</button>';
    html += '</div>';

    // View toggle buttons
    html += '<div class="view-toggle">';
    if (hasCoordinates) {
        html += '<button class="view-btn active" onclick="switchView(this, \'map\')"><i class="fas fa-map"></i> Bản đồ</button>';
    }
    html += '<button class="view-btn' + (!hasCoordinates ? ' active' : '') + '" onclick="switchView(this, \'table\')"><i class="fas fa-table"></i> Bảng</button>';
    html += '<button class="view-btn" onclick="switchView(this, \'grid\')"><i class="fas fa-th"></i> Thẻ</button>';
    html += '</div>';
    html += '</div></div>';

    // Content area
    html += '<div class="data-content">';

    // Map view
    if (hasCoordinates) {
        html += `<div class="view-content map-view active">`;
        html += '<div class="map-container">';
        html += '<div class="map-header">';
        html += '<div class="map-title"><i class="fas fa-map-marker-alt"></i>Bản đồ khu công nghiệp</div>';
        html += '<div class="map-controls">';
        html += '<button class="map-btn" onclick="toggleMapLayer(\'satellite\')"><i class="fas fa-satellite"></i> Vệ tinh</button>';
        html += '<button class="map-btn active" onclick="toggleMapLayer(\'street\')"><i class="fas fa-road"></i> Đường phố</button>';
        html += '</div></div>';
        html += `<div id="${mapId}" class="map-view-container" style="height: 500px; border-radius: 8px;"></div>`;
        html += `<div class="map-info">• Click vào cụm để zoom • Click vào điểm để xem chi tiết • Tổng: ${payload.count} điểm</div>`;
        html += '</div></div>';
    }

    // Table view
    html += `<div class="view-content table-view${!hasCoordinates ? ' active' : ''}">`;
    html += createTableView(payload.data);
    html += '</div>';

    // Grid view
    html += '<div class="view-content grid-view">';
    html += createGridView(payload.data);
    html += '</div>';

    html += '</div></div>';

    // Store map data for initialization
    if (hasCoordinates) {
        window.pendingMapData = { mapId, mapIntent };
    }

    return html;
}

// Initialize chart
function initializeChart(chartId, data) {
    const ctx = document.getElementById(chartId);
    if (!ctx || typeof Chart === 'undefined') return;

    // Sample chart data - you would use real data from payload
    const chartData = {
        labels: ['Hà Nội', 'TP.HCM', 'Đà Nẵng', 'Bắc Ninh', 'Thanh Hóa'],
        datasets: [{
            label: 'Số lượng KCN',
            data: [45, 67, 23, 33, 28],
            backgroundColor: [
                'rgba(52, 152, 219, 0.8)',
                'rgba(231, 76, 60, 0.8)',
                'rgba(46, 204, 113, 0.8)',
                'rgba(155, 89, 182, 0.8)',
                'rgba(243, 156, 18, 0.8)'
            ],
            borderColor: [
                'rgba(52, 152, 219, 1)',
                'rgba(231, 76, 60, 1)',
                'rgba(46, 204, 113, 1)',
                'rgba(155, 89, 182, 1)',
                'rgba(243, 156, 18, 1)'
            ],
            borderWidth: 2
        }]
    };

    currentChart = new Chart(ctx, {
        type: 'bar',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                title: {
                    display: true,
                    text: 'Thống kê Khu Công Nghiệp'
                }
            },
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

// Switch chart type
function switchChart(button, chartType) {
    const container = button.closest('.chart-container');
    const chartButtons = container.querySelectorAll('.chart-btn');

    // Update button states
    chartButtons.forEach(btn => btn.classList.remove('active'));
    button.classList.add('active');

    // Update chart type
    if (currentChart) {
        currentChart.config.type = chartType;
        currentChart.update();
    }
}

// Add message to chat
function addMessage(text, sender, isHtml = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;

    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    avatarDiv.innerHTML = sender === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';

    if (isHtml) {
        textDiv.innerHTML = text;
    } else {
        textDiv.textContent = text;
    }

    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    timeDiv.textContent = new Date().toLocaleTimeString('vi-VN', {
        hour: '2-digit',
        minute: '2-digit'
    });

    contentDiv.appendChild(textDiv);
    contentDiv.appendChild(timeDiv);
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);

    messagesArea.appendChild(messageDiv);
    scrollToBottom();
}

// Show typing indicator
function showTypingIndicator() {
    typingIndicator.style.display = 'flex';
    scrollToBottom();
}

// Hide typing indicator
function hideTypingIndicator() {
    typingIndicator.style.display = 'none';
}

// Scroll to bottom
function scrollToBottom() {
    setTimeout(() => {
        messagesArea.scrollTop = messagesArea.scrollHeight;
    }, 100);
}

// Contact modal functions
function showContactModal(originalMessage) {
    document.getElementById('originalQuestion').value = originalMessage;
    contactModal.style.display = 'block';
    document.getElementById('contactName').focus();
}

function closeContactModal() {
    contactModal.style.display = 'none';
    contactForm.reset();
}

async function submitContact(e) {
    e.preventDefault();

    const formData = new FormData(contactForm);
    const contactData = {
        original_question: formData.get('original_question'),
        name: formData.get('name'),
        phone: formData.get('phone')
    };

    try {
        const response = await fetch('/submit-contact', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(contactData)
        });

        const data = await response.json();

        if (response.ok) {
            addMessage(data.message, 'bot');
            closeContactModal();
        } else {
            alert('Lỗi: ' + (data.detail || 'Không thể gửi thông tin'));
        }
    } catch (error) {
        alert('Lỗi kết nối. Vui lòng thử lại sau.');
        console.error('Error:', error);
    }
}

// Utility functions
function formatMessage(text) {
    // Convert markdown-like formatting to HTML
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}

// Export to JSON function
async function exportToJSON(province, type) {
    console.log('🔄 Exporting JSON for:', province, type);

    try {
        // Tạo query để export
        const exportQuery = `danh sách ${type} ở ${province}`;

        const response = await fetch('/export-json', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                question: exportQuery
            })
        });

        if (response.ok) {
            // Lấy filename từ header
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'kcn_export.json';

            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename=(.+)/);
                if (filenameMatch) {
                    filename = filenameMatch[1];
                }
            }

            // Download file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            // Show success message
            addMessage(`✅ Đã xuất file JSON: ${filename}`, 'bot');

        } else {
            const errorData = await response.json();
            addMessage(`❌ Lỗi xuất JSON: ${errorData.detail}`, 'bot');
        }

    } catch (error) {
        console.error('Export JSON error:', error);
        addMessage('❌ Lỗi kết nối khi xuất JSON. Vui lòng thử lại.', 'bot');
    }
}

// Export chart data to JSON function
async function exportChartToJSON(province, type, metric) {
    console.log('📊 Exporting Chart JSON for:', province, type, metric);

    try {
        // Tạo query để export biểu đồ
        const exportQuery = `vẽ biểu đồ ${metric} ${type} ở ${province}`;

        const response = await fetch('/export-chart-json', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                question: exportQuery
            })
        });

        if (response.ok) {
            // Lấy filename từ header
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'chart_export.json';

            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename=(.+)/);
                if (filenameMatch) {
                    filename = filenameMatch[1];
                }
            }

            // Download file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            // Show success message
            addMessage(`✅ Đã xuất file JSON biểu đồ: ${filename}`, 'bot');

        } else {
            const errorData = await response.json();
            addMessage(`❌ Lỗi xuất JSON biểu đồ: ${errorData.detail}`, 'bot');
        }

    } catch (error) {
        console.error('Export Chart JSON error:', error);
        addMessage('❌ Lỗi kết nối khi xuất JSON biểu đồ. Vui lòng thử lại.', 'bot');
    }
}