// API URL - Change this to your Railway backend URL when deployed
const API_URL = 'https://stock-bot-app-production.up.railway.app'; // For local testing
// For production, change to: const API_URL = 'https://your-railway-url';

// Handle Login
const loginForm = document.getElementById('loginForm');

if (loginForm) {
  loginForm.addEventListener('submit', async (e) => {

    e.preventDefault();

    const email =
      document.getElementById('email').value;

    const password =
      document.getElementById('password').value;

    try {

      const response =
        await fetch(`${API_URL}/api/login`, {
          method: 'POST',

          headers: {
            'Content-Type': 'application/json'
          },

          body: JSON.stringify({
            email,
            password
          })
        });

      const data =
        await response.json();

      if (data.success) {

        localStorage.setItem(
          'token',
          data.token
        );

        localStorage.setItem(
          'user',
          JSON.stringify(data.user)
        );

        window.location.href =
          'dashboard.html';

      } else {

        alert(
          data.message || 'Invalid credentials'
        );

      }

    } catch (error) {

      console.error(
        'Login error:',
        error
      );

      alert(
        'Login failed. Please try again.'
      );

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
            const response = await fetch(`https://stock-bot-app-production.up.railway.app/api/signup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, email, password})
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

  const token =
    localStorage.getItem('token');

  const user =
    localStorage.getItem('user');

  if (
    (!token || !user) &&
    window.location.pathname.includes('dashboard')
  ) {

    window.location.href =
      'login.html';

  }

}
async function loadAlerts(){

const user =
JSON.parse(
localStorage.getItem(
'user'
)
)

if(!user)return

const response =
await fetch(

`${API_URL}/api/user/${user.id}/alerts/check`

)

const data =
await response.json()

const el =
document.getElementById(
'alertsList'
)

if(
!data.triggered_alerts ||
!data.triggered_alerts.length
){

el.innerHTML =
'No alerts triggered'

return

}

el.innerHTML =
data.triggered_alerts
.map(alert=>`

<div
style="
padding:10px;
margin-bottom:8px;
background:#fff7ed;
border-radius:8px;
"
>

🔔

${alert.symbol}

—

${alert.alert_type.replace(
'_',
' '
)}

</div>

`).join('')

}

loadAlerts()
checkAuth();