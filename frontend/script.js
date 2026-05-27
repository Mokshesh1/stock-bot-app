// ==================== API CONFIGURATION ====================

// Dynamically choose local backend during development.
const API_URL = (
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1' ||
  window.location.protocol === 'file:'
)
  ? 'http://localhost:5000'
  : 'https://stock-bot-app-production.up.railway.app';

// ==================== AUTHENTICATION ====================

// Handle Login
const loginForm = document.getElementById('loginForm');

if (loginForm) {
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    try {
      const response = await fetch(`${API_URL}/api/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email, password })
      });

      const data = await response.json();

      if (data.success) {
        // NEW: Store access_token and refresh_token (not old 'token')
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('refresh_token', data.refresh_token);
        localStorage.setItem('user', JSON.stringify(data.user));

        console.log('✅ Login successful');
        window.location.href = 'dashboard.html';

      } else {
        alert(data.message || 'Invalid credentials');
      }

    } catch (error) {
      console.error('Login error:', error);
      alert('Login failed. Please try again.');
    }
  });
}

// Handle Signup
const signupForm = document.getElementById('signupForm');

if (signupForm) {
  signupForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const name = document.getElementById('name').value;
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    try {
      const response = await fetch(`${API_URL}/api/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password })
      });

      const data = await response.json();

      if (data.success) {
        alert('Signup successful! Please login.');
        window.location.href = 'login.html';
      } else {
        alert('Signup failed: ' + data.message);
      }

    } catch (error) {
      console.error('Signup error:', error);
      alert('Signup failed. Please try again.');
    }
  });
}

// ==================== AUTHORIZATION ====================

/**
 * Get the access token from localStorage
 * Returns null if not found or expired
 */
function getAccessToken() {
  const token = localStorage.getItem('access_token');
  if (!token) {
    console.warn('No access token found. User not logged in.');
    return null;
  }
  return token;
}

/**
 * Make authenticated API request
 * Automatically includes JWT token in Authorization header
 */
async function authenticatedFetch(endpoint, options = {}) {
  const token = getAccessToken();

  if (!token) {
    console.error('Not authenticated. Redirecting to login.');
    window.location.href = 'login.html';
    return null;
  }

  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    ...options.headers
  };

  const url = endpoint.startsWith('http://') || endpoint.startsWith('https://')
    ? endpoint
    : `${API_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers
  });

  // Handle 401 (token expired/invalid)
  if (response.status === 401) {
    console.error('Token invalid or expired. Logging out.');
    localStorage.clear();
    window.location.href = 'login.html';
    return null;
  }

  return response;
}

// ==================== USER MANAGEMENT ====================

// Check if user is logged in
function checkAuth() {
  const token = localStorage.getItem('access_token');
  const user = localStorage.getItem('user');

  // If accessing dashboard but not logged in, redirect to login
  if ((!token || !user) && window.location.pathname.includes('dashboard')) {
    window.location.href = 'login.html';
  }
}

// Handle Logout
async function logout() {
  try {
    const token = localStorage.getItem('access_token');
    
    if (token) {
      // Tell backend to blacklist the token
      await authenticatedFetch('/api/logout', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
    }
  } catch (error) {
    console.error('Logout error:', error);
  } finally {
    // Clear local storage
    localStorage.clear();
    // Redirect to login
    window.location.href = 'login.html';
  }
}

// ==================== DASHBOARD DATA ====================

// Load user stats
async function loadStats(userId) {
  try {
    const response = await authenticatedFetch(`/api/user/${userId}/stats`);
    
    if (!response || !response.ok) {
      console.error('Failed to load stats');
      return;
    }

    const data = await response.json();

    // Update stats display
    const statsEl = document.getElementById('userStats');
    if (statsEl && data.success) {
      statsEl.innerHTML = `
        <div>Total Trades: ${data.total_trades}</div>
        <div>Win Rate: ${data.win_rate}%</div>
        <div>Avg Profit: ₹${data.avg_profit}</div>
      `;
    }

  } catch (error) {
    console.error('Error loading stats:', error);
  }
}

// Load user trades
async function loadTrades(userId) {
  try {
    const response = await authenticatedFetch(`/api/user/${userId}/trades`);
    
    if (!response || !response.ok) {
      console.error('Failed to load trades');
      return;
    }

    const data = await response.json();

    // Update trades display
    const tradesEl = document.getElementById('tradesList');
    if (tradesEl && data.success) {
      if (data.trades.length === 0) {
        tradesEl.innerHTML = '<p>No trades yet</p>';
        return;
      }

      tradesEl.innerHTML = data.trades.map(trade => `
        <div style="padding: 10px; border: 1px solid #ccc; margin-bottom: 10px; border-radius: 8px;">
          <strong>${trade.symbol}</strong><br/>
          Entry: ₹${trade.entry_price}<br/>
          Exit: ${trade.exit_price ? '₹' + trade.exit_price : 'Open'}<br/>
          P&L: ₹${trade.profit_loss || 'N/A'}<br/>
          Status: ${trade.status}
        </div>
      `).join('');
    }

  } catch (error) {
    console.error('Error loading trades:', error);
  }
}

// Load alerts
async function loadAlerts(userId) {
  try {
    const response = await authenticatedFetch(`/api/user/${userId}/alerts/check`);
    
    if (!response || !response.ok) {
      console.error('Failed to check alerts');
      return;
    }

    const data = await response.json();

    // Update alerts display
    const alertsEl = document.getElementById('alertsList');
    if (alertsEl && data.success) {
      if (!data.triggered_alerts || data.triggered_alerts.length === 0) {
        alertsEl.innerHTML = '<p>No alerts triggered</p>';
        return;
      }

      alertsEl.innerHTML = data.triggered_alerts.map(alert => `
        <div style="
          padding: 10px;
          margin-bottom: 8px;
          background: #fff7ed;
          border-radius: 8px;
          border-left: 4px solid #ff6b35;
        ">
          🔔 <strong>${alert.symbol}</strong> — ${alert.alert_type.replace(/_/g, ' ')}
          ${alert.target_value ? ` (Target: ${alert.target_value})` : ''}
        </div>
      `).join('');
    }

  } catch (error) {
    console.error('Error loading alerts:', error);
  }
}

// Load watchlist
async function loadWatchlist(userId) {
  try {
    const response = await authenticatedFetch(`/api/user/${userId}/watchlist`);
    
    if (!response || !response.ok) {
      console.error('Failed to load watchlist');
      return;
    }

    const data = await response.json();

    // Update watchlist display
    const watchlistEl = document.getElementById('watchlistList');
    if (watchlistEl && data.success) {
      if (data.watchlist.length === 0) {
        watchlistEl.innerHTML = '<p>No watchlist items</p>';
        return;
      }

      watchlistEl.innerHTML = data.watchlist.map(item => `
        <div style="
          padding: 10px;
          margin-bottom: 8px;
          background: #f0f0f0;
          border-radius: 8px;
          display: flex;
          justify-content: space-between;
          align-items: center;
        ">
          <span><strong>${item.symbol}</strong></span>
          <button onclick="removeFromWatchlist(${item.id}, ${userId})" style="
            padding: 5px 10px;
            background: #ff6b6b;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
          ">Remove</button>
        </div>
      `).join('');
    }

  } catch (error) {
    console.error('Error loading watchlist:', error);
  }
}

// Remove from watchlist
async function removeFromWatchlist(itemId, userId) {
  try {
    const response = await authenticatedFetch(`/api/user/${userId}/watchlist/${itemId}`, {
      method: 'DELETE'
    });

    if (response && response.ok) {
      alert('Removed from watchlist');
      loadWatchlist(userId);
    } else {
      alert('Failed to remove from watchlist');
    }

  } catch (error) {
    console.error('Error removing from watchlist:', error);
  }
}

// ==================== INITIALIZATION ====================

// Run on page load
document.addEventListener('DOMContentLoaded', () => {
  // Check if user is authenticated
  checkAuth();

  // Load dashboard data if on dashboard page
  const user = localStorage.getItem('user');
  if (user && window.location.pathname.includes('dashboard')) {
    try {
      const userData = JSON.parse(user);
      const userId = userData.id;

      // Load all dashboard sections
      loadStats(userId);
      loadTrades(userId);
      loadAlerts(userId);
      loadWatchlist(userId);

      // Refresh alerts every 30 seconds
      setInterval(() => loadAlerts(userId), 30000);

    } catch (error) {
      console.error('Error parsing user data:', error);
    }
  }
});

// ==================== UTILITY FUNCTIONS ====================

/**
 * Decode JWT token to see claims (for debugging)
 */
function decodeToken() {
  const token = localStorage.getItem('access_token');
  if (!token) {
    console.log('No token found');
    return null;
  }

  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64).split('').map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('')
    );
    return JSON.parse(jsonPayload);
  } catch (error) {
    console.error('Error decoding token:', error);
    return null;
  }
}

// Optional: Add a logout button
function addLogoutButton() {
  const button = document.createElement('button');
  button.textContent = 'Logout';
  button.style.cssText = 'position: fixed; top: 10px; right: 10px; padding: 10px 20px; background: #ff6b6b; color: white; border: none; border-radius: 4px; cursor: pointer;';
  button.onclick = logout;
  document.body.appendChild(button);
}

// Uncomment to add logout button automatically
 if (localStorage.getItem('access_token')) {
   addLogoutButton();
 }