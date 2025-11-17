// API Configuration
const API_BASE_URL = 'http://localhost:5000/api';

// State
let currentMovieForRating = null;

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    initializeTabs();
    initializeUpload();
    initializeSearch();
    initializeRecommendations();
    loadCollection();
});

// Tab Management
function initializeTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.dataset.tab;

            // Remove active class from all
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));

            // Add active class to clicked
            button.classList.add('active');
            document.getElementById(`${tabName}-tab`).classList.add('active');

            // Load collection when switching to collection tab
            if (tabName === 'collection') {
                loadCollection();
            }
        });
    });
}

// CSV Upload
function initializeUpload() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('csvFile');

    // Click to upload
    uploadArea.addEventListener('click', () => fileInput.click());

    // File selection
    fileInput.addEventListener('change', handleFileSelect);

    // Drag and drop
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('drag-over');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('drag-over');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        handleFile(file);
    }
}

async function handleFile(file) {
    if (!file.name.endsWith('.csv')) {
        showStatus('importStatus', 'Please select a CSV file', 'error');
        return;
    }

    showLoading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_BASE_URL}/upload-csv`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showStatus('importStatus', data.message, 'success');
            
            if (data.errors && data.errors.length > 0) {
                const errorList = data.errors.slice(0, 5).join('<br>');
                showStatus('importStatus', 
                    `${data.message}<br><br>Some errors occurred:<br>${errorList}`, 
                    'info');
            }
        } else {
            showStatus('importStatus', data.error || 'Import failed', 'error');
        }
    } catch (error) {
        console.error('Upload error:', error);
        showStatus('importStatus', 'Network error. Please check if the backend is running.', 'error');
    } finally {
        showLoading(false);
    }
}

// Movie Search
function initializeSearch() {
    const searchForm = document.getElementById('searchForm');
    searchForm.addEventListener('submit', handleSearch);
}

async function handleSearch(event) {
    event.preventDefault();

    const title = document.getElementById('movieTitle').value.trim();
    const year = document.getElementById('movieYear').value;

    if (!title) return;

    showLoading(true);

    try {
        const params = { title };
        if (year) params.year = year;

        const response = await fetch(`${API_BASE_URL}/add-movie`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });

        const data = await response.json();

        if (response.ok && data.matches) {
            displaySearchResults(data.matches);
        } else {
            showStatus('addStatus', data.error || data.message || 'No results found', 'error');
            document.getElementById('searchResults').innerHTML = '';
        }
    } catch (error) {
        console.error('Search error:', error);
        showStatus('addStatus', 'Network error. Please check if the backend is running.', 'error');
    } finally {
        showLoading(false);
    }
}

function displaySearchResults(matches) {
    const resultsContainer = document.getElementById('searchResults');
    
    if (matches.length === 0) {
        resultsContainer.innerHTML = '<p>No results found</p>';
        return;
    }

    resultsContainer.innerHTML = `
        <h3>Select a movie:</h3>
        ${matches.map(movie => `
            <div class="search-result-item" onclick="selectMovie(${movie.tmdb_id})">
                <img src="${movie.poster_path || 'https://via.placeholder.com/80x120?text=No+Image'}" 
                     alt="${movie.title}" 
                     class="search-result-poster">
                <div class="search-result-info">
                    <div class="search-result-title">${movie.title} (${movie.year || 'N/A'})</div>
                    <div class="search-result-meta">${movie.overview ? movie.overview.substring(0, 150) + '...' : 'No description available'}</div>
                </div>
            </div>
        `).join('')}
    `;
}

async function selectMovie(tmdbId) {
    // Show rating form
    const resultsContainer = document.getElementById('searchResults');
    resultsContainer.innerHTML = `
        <div class="card">
            <h3>Rate this movie</h3>
            <form id="ratingForm" onsubmit="submitMovieRating(event, ${tmdbId})">
                <div class="form-group">
                    <input type="number" id="userRating" placeholder="Rating (0-10)" 
                           min="0" max="10" step="0.5" required>
                    <input type="date" id="watchDate" placeholder="Watch Date">
                </div>
                <button type="submit" class="btn-primary">Add to Collection</button>
            </form>
        </div>
    `;
}

async function submitMovieRating(event, tmdbId) {
    event.preventDefault();

    const rating = parseFloat(document.getElementById('userRating').value);
    const watchDate = document.getElementById('watchDate').value;

    showLoading(true);

    try {
        const response = await fetch(`${API_BASE_URL}/add-movie`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tmdb_id: tmdbId,
                rating: rating,
                watch_date: watchDate || null
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showStatus('addStatus', data.message, 'success');
            document.getElementById('searchForm').reset();
            document.getElementById('searchResults').innerHTML = '';
        } else {
            showStatus('addStatus', data.error || 'Failed to add movie', 'error');
        }
    } catch (error) {
        console.error('Add movie error:', error);
        showStatus('addStatus', 'Network error. Please check if the backend is running.', 'error');
    } finally {
        showLoading(false);
    }
}

// Recommendations
function initializeRecommendations() {
    const generateBtn = document.getElementById('generateBtn');
    generateBtn.addEventListener('click', generateRecommendations);
}

async function generateRecommendations() {
    showLoading(true);
    document.getElementById('recommendationsList').innerHTML = '';

    try {
        const response = await fetch(`${API_BASE_URL}/recommendations`);
        const data = await response.json();

        if (response.ok && data.success) {
            displayRecommendations(data.recommendations);
            showStatus('recommendationsStatus', 
                `Found ${data.count} personalized recommendations for you!`, 
                'success');
        } else {
            showStatus('recommendationsStatus', data.error || data.message, 'error');
        }
    } catch (error) {
        console.error('Recommendations error:', error);
        showStatus('recommendationsStatus', 
            'Network error. Please check if the backend is running.', 
            'error');
    } finally {
        showLoading(false);
    }
}

function displayRecommendations(recommendations) {
    const container = document.getElementById('recommendationsList');

    if (recommendations.length === 0) {
        container.innerHTML = '<p>No recommendations available</p>';
        return;
    }

    container.innerHTML = recommendations.map(movie => `
        <div class="movie-card" onclick="showMovieDetails(${movie.tmdb_id})">
            <img src="${movie.poster_path || 'https://via.placeholder.com/200x300?text=No+Image'}" 
                 alt="${movie.title}" 
                 class="movie-poster">
            <div class="movie-info">
                <div class="movie-title">${movie.title}</div>
                <div class="movie-meta">${movie.year || 'N/A'} • ${movie.genres ? movie.genres.slice(0, 2).join(', ') : 'N/A'}</div>
                <div class="match-score">${movie.match_score}% Match</div>
                <div class="movie-reasoning">${movie.reasoning}</div>
            </div>
        </div>
    `).join('');
}

// Collection
async function loadCollection() {
    try {
        const response = await fetch(`${API_BASE_URL}/movies`);
        const data = await response.json();

        if (response.ok) {
            displayCollection(data.movies, data.count);
        }
    } catch (error) {
        console.error('Load collection error:', error);
    }
}

function displayCollection(movies, count) {
    const countContainer = document.getElementById('collectionCount');
    const listContainer = document.getElementById('collectionList');

    countContainer.textContent = `You have ${count} movie${count !== 1 ? 's' : ''} in your collection`;

    if (movies.length === 0) {
        listContainer.innerHTML = '<p>No movies in your collection yet. Start by importing a CSV or adding movies manually!</p>';
        return;
    }

    listContainer.innerHTML = movies.map(movie => `
        <div class="movie-card" onclick="showMovieDetails(${movie.tmdb_id})">
            <img src="${movie.poster_path || 'https://via.placeholder.com/200x300?text=No+Image'}" 
                 alt="${movie.title}" 
                 class="movie-poster">
            <div class="movie-info">
                <div class="movie-title">${movie.title}</div>
                <div class="movie-meta">${movie.year || 'N/A'} • ${movie.genres ? movie.genres.slice(0, 2).join(', ') : 'N/A'}</div>
                ${movie.rating ? `<div class="match-score">Your Rating: ${movie.rating}/10</div>` : ''}
            </div>
        </div>
    `).join('');
}

// Movie Details Modal
async function showMovieDetails(tmdbId) {
    showLoading(true);

    try {
        const response = await fetch(`${API_BASE_URL}/movie/${tmdbId}`);
        const movie = await response.json();

        if (response.ok) {
            displayMovieModal(movie);
        }
    } catch (error) {
        console.error('Movie details error:', error);
    } finally {
        showLoading(false);
    }
}

function displayMovieModal(movie) {
    const modal = document.getElementById('movieModal');
    const detailsContainer = document.getElementById('movieDetails');

    detailsContainer.innerHTML = `
        <div class="movie-detail-header" style="background-image: url('${movie.backdrop_path || movie.poster_path || ''}')">
            <div class="movie-detail-overlay">
                <h2>${movie.title} (${movie.year || 'N/A'})</h2>
                <p>${movie.genres ? movie.genres.join(', ') : 'N/A'}</p>
            </div>
        </div>
        <div class="movie-detail-body">
            <div class="movie-detail-section">
                <h3>Overview</h3>
                <p>${movie.overview || 'No overview available'}</p>
            </div>
            ${movie.director ? `
                <div class="movie-detail-section">
                    <h3>Director</h3>
                    <p>${movie.director}</p>
                </div>
            ` : ''}
            ${movie.cast && movie.cast.length > 0 ? `
                <div class="movie-detail-section">
                    <h3>Cast</h3>
                    <div class="cast-list">
                        ${movie.cast.map(actor => `
                            <span class="cast-member">${actor.name}</span>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
            <div class="movie-detail-section">
                <h3>Details</h3>
                <p><strong>Runtime:</strong> ${movie.runtime ? movie.runtime + ' minutes' : 'N/A'}</p>
                <p><strong>Rating:</strong> ${movie.rating ? movie.rating + '/10' : 'N/A'}</p>
            </div>
        </div>
    `;

    modal.classList.add('show');

    // Close modal
    const closeBtn = document.querySelector('.modal-close');
    closeBtn.onclick = () => modal.classList.remove('show');

    modal.onclick = (e) => {
        if (e.target === modal) {
            modal.classList.remove('show');
        }
    };
}

// Utility Functions
function showStatus(elementId, message, type) {
    const statusElement = document.getElementById(elementId);
    statusElement.innerHTML = message;
    statusElement.className = `status-message ${type} show`;

    setTimeout(() => {
        statusElement.classList.remove('show');
    }, 5000);
}

function showLoading(show) {
    const spinner = document.getElementById('loadingSpinner');
    if (show) {
        spinner.classList.add('show');
    } else {
        spinner.classList.remove('show');
    }
}
