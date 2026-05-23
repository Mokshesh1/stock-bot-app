// API URL - Change this to your Railway backend URL when deployed
const API_URL = 'http://localhost:5000'; // For local testing
// For production, change to: const API_URL = 'https://your-railway-url';

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
        const zerodha_key = document.getElementById('zerodha_key').value || null;

        try {
            const response = await fetch(`${API_URL}/api/signup`, {
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
        } catch (error) {
            console.error('Signup error:', error);
            alert('Signup failed. Please try again.');
        }
    });
}

// Check if user is logged in
function checkAuth() {
    const token = localStorage.getItem('token');
    if (!token && window.location.pathname.includes('dashboard')) {
        window.location.href = 'login.html';
    }
}

checkAuth();