// Import the functions you need from the SDKs you need
import { initializeApp, getApp, getApps } from "firebase/app";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
const firebaseConfig = {
  "projectId": "nestedge-navigator",
  "appId": "1:227792157644:web:dd1030c6851a54b26a7b69",
  "storageBucket": "nestedge-navigator.firebasestorage.app",
  "apiKey": "AIzaSyAxmTRhgaWrmOWeM-unL_kO8kcQ8GoLn4w",
  "authDomain": "nestedge-navigator.firebaseapp.com",
  "measurementId": "",
  "messagingSenderId": "227792157644"
};

// Initialize Firebase
const app = !getApps().length ? initializeApp(firebaseConfig) : getApp();

export { app };
