// AuthContext.js
// Provides global authentication state (JWT, login/logout) using React Context.
// Allows any component to access or update auth info without prop drilling.
import React, { createContext, useContext, useState } from 'react';

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [jwt, _setJwt] = useState(() => localStorage.getItem('ai_study_helper_jwt'));

  // Wrap setJwt to also persist in localStorage
  const setJwt = token => {
    if (token) localStorage.setItem('ai_study_helper_jwt', token);
    else localStorage.removeItem('ai_study_helper_jwt');
    _setJwt(token);
  };

  // Clears JWT from state & storage
  const logout = () => setJwt(null);

  return (
    <AuthContext.Provider value={{ jwt, setJwt, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}