# Add at top:
const API_URL = 'https://your-railway-url';

# Change all fetches:
fetch(`${API_URL}/api/login`, ...)
fetch(`${API_URL}/api/signup`, ...)
# etc

// Handle Login
document.getElementById('loginForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    const response = await fetch('http://localhost:5000/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });

    const data = await response.json();
    if (data.success) {
        localStorage.setItem('token', data.token);
        window.location.href = 'dashboard.html';
    } else {
        alert('Invalid credentials');
    }
});

// Handle Signup
document.getElementById('signupForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('name').value;
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    const zerodha_key = document.getElementById('zerodha_key').value || null; // Changed from: required to optional

    const response = await fetch('http://localhost:5000/api/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password, zerodha_key })
    });

    const data = await response.json();
    if (data.success) {
        alert('Signup successful! Please login.');
        window.location.href = 'login.html';
    } else {
        alert('Signup failed: ' + data.message);
    }
});

// Check if user is logged in
function checkAuth() {
    const token = localStorage.getItem('token');
    if (!token && window.location.pathname.includes('dashboard')) {
        window.location.href = 'login.html';
    }
}

checkAuth();