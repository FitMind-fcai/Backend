# Authentication Flow Guide

## Overview
This guide explains how to implement authentication checking at your splash screen.

## Backend Endpoints

### 1. **POST /auth/signup** - Create New User
Register a new user account.

**Request Body:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "age": 25,
  "password": "securepassword123"
}
```

**Response:**
```json
{
  "id": 1,
  "name": "John Doe",
  "email": "john@example.com",
  "age": 25
}
```

---

### 2. **POST /auth/login** - Login User
Authenticate user and get JWT token.

**Request (Form Data):**
```
username: john@example.com
password: securepassword123
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "name": "John Doe",
    "email": "john@example.com",
    "age": 25
  }
}
```

---

### 3. **GET /auth/me** - Get Current User (Splash Screen Check)
**This is the main endpoint for your splash screen!**

Check if the stored token is valid and get user information.

**Request Headers:**
```
Authorization: Bearer <your-jwt-token>
```

**Response (Success - 200):**
```json
{
  "id": 1,
  "name": "John Doe",
  "email": "john@example.com",
  "age": 25
}
```

**Response (Failure - 401):**
```json
{
  "detail": "Could not validate credentials"
}
```

---

### 4. **POST /auth/verify-token** - Verify Token Only
Simpler alternative if you only need to check token validity.

**Request Headers:**
```
Authorization: Bearer <your-jwt-token>
```

**Response (Success - 200):**
```json
{
  "valid": true,
  "user_id": 1,
  "email": "john@example.com"
}
```

**Response (Failure - 401):**
```json
{
  "detail": "Could not validate credentials"
}
```

---

## Splash Screen Implementation Logic

### Client-Side Flow (Pseudocode)

```javascript
async function checkAuthenticationOnSplashScreen() {
  // 1. Check if token exists in local storage
  const token = localStorage.getItem('access_token');
  
  if (!token) {
    // No token found → redirect to auth/login screens
    navigateToAuthScreens();
    return;
  }
  
  // 2. Verify token with backend
  try {
    const response = await fetch('http://localhost:8000/auth/me', {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    
    if (response.ok) {
      // Token is valid → get user data and redirect to home
      const userData = await response.json();
      setCurrentUser(userData);
      navigateToHomeScreen();
    } else {
      // Token is invalid/expired → clear storage and redirect to auth
      localStorage.removeItem('access_token');
      navigateToAuthScreens();
    }
  } catch (error) {
    // Network error or server down → redirect to auth screens
    console.error('Auth check failed:', error);
    navigateToAuthScreens();
  }
}

// Call this function when splash screen loads
checkAuthenticationOnSplashScreen();
```

---

## Python Client Example

```python
import requests

BASE_URL = "http://localhost:8000"

def check_authentication_at_splash():
    """
    Function to run at splash screen startup.
    Returns: (is_authenticated, user_data or None)
    """
    # Try to get stored token (from file, config, etc.)
    token = get_stored_token()  # Your storage mechanism
    
    if not token:
        print("No token found - redirect to auth screens")
        return False, None
    
    # Verify token with backend
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(f"{BASE_URL}/auth/me", headers=headers)
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"Authenticated as: {user_data['name']}")
            return True, user_data
        else:
            print("Token invalid - redirect to auth screens")
            clear_stored_token()
            return False, None
            
    except requests.exceptions.RequestException as e:
        print(f"Error checking authentication: {e}")
        return False, None


def login_user(email: str, password: str):
    """
    Login user and store token.
    """
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": email, "password": password}
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data["access_token"]
        user = data["user"]
        
        # Store token for future use
        store_token(token)
        
        print(f"Login successful! Welcome {user['name']}")
        return True, user
    else:
        print("Login failed!")
        return False, None
```

---

## Mobile App (Flutter/React Native) Example

### Flutter Example
```dart
Future<void> checkAuthOnSplashScreen() async {
  final prefs = await SharedPreferences.getInstance();
  final token = prefs.getString('access_token');
  
  if (token == null) {
    // Navigate to auth screens
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (context) => AuthScreen()),
    );
    return;
  }
  
  // Verify token
  try {
    final response = await http.get(
      Uri.parse('http://localhost:8000/auth/me'),
      headers: {'Authorization': 'Bearer $token'},
    );
    
    if (response.statusCode == 200) {
      final userData = jsonDecode(response.body);
      // Navigate to home screen
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (context) => HomeScreen(user: userData),
        ),
      );
    } else {
      // Token invalid, go to auth
      await prefs.remove('access_token');
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (context) => AuthScreen()),
      );
    }
  } catch (e) {
    // Error, go to auth
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (context) => AuthScreen()),
    );
  }
}
```

---

## Security Notes

1. **Change the SECRET_KEY**: In `routes/auth.py`, move the `SECRET_KEY` to environment variables
2. **Use HTTPS**: Always use HTTPS in production
3. **Token Expiration**: Tokens expire after 30 minutes (configurable)
4. **Secure Storage**: Store tokens securely on the client (KeyChain, encrypted storage, etc.)
5. **Refresh Tokens**: Consider implementing refresh tokens for longer sessions

---

## Testing with cURL

```bash
# 1. Signup
curl -X POST "http://localhost:8000/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"name":"John Doe","email":"john@example.com","age":25,"password":"password123"}'

# 2. Login
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=john@example.com&password=password123"

# 3. Check Authentication (replace TOKEN with actual token)
curl -X GET "http://localhost:8000/auth/me" \
  -H "Authorization: Bearer TOKEN"

# 4. Verify Token
curl -X POST "http://localhost:8000/auth/verify-token" \
  -H "Authorization: Bearer TOKEN"
```

---

## Summary

**For your splash screen:**
1. Check if token exists in storage
2. If yes → Call `GET /auth/me` with the token
3. If response is 200 → User is authenticated → Go to home screen
4. If response is 401 or no token → Go to auth/login screens

This ensures users don't have to login every time they open your app!
