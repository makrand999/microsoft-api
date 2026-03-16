# Microsoft Learn Quiz & Module Auto Solver

This project automates completing **Microsoft Learn quizzes, modules, and learning paths**.
It detects quiz units, submits answers, retrieves the correct answers returned by Microsoft, and completes the quizzes automatically. It can also **automatically complete modules and entire learning paths**.

## Features

* Automatically detects and solves **quiz questions**
* Retrieves **correct answers from Microsoft Learn responses**
* Automatically **completes modules**
* Automatically **completes learning paths**
* Uses **browser cookies from a logged-in session** for authentication
* Currently configured for **C# course (Part 1–6)** but can be modified for other Microsoft Learn courses

---

## Requirements

* Python **3.8+**
* Required package:

```bash
pip install requests
```

---

## Setup

### 1. Export Cookies from Your Logged-in Browser

The script requires cookies from a **logged-in Microsoft Learn session**.

Steps:

1. Install the **Cookie-Editor** browser extension.
2. Go to **https://learn.microsoft.com** and make sure you are **logged in**.
3. Open the **Cookie-Editor extension**.
4. Export cookies in **JSON format**.
5. Copy the exported JSON.

---

### 2. Create `settings.json`

Create a file named:

```
settings.json
```

Place it in the **same folder as the script** and paste the exported cookies inside.

Example:

```json
{
  "cookies": [
    {
      "name": "cookie_name",
      "value": "cookie_value"
    }
  ]
}
```

---

## Course Configuration

The repository currently has **C# course units (Part 1–6) hardcoded**.

If you want to use the script for another Microsoft Learn course:

1. Replace the course URLs or unit IDs in the script.
2. Adjust module or learning path identifiers if necessary.

---

## How Quiz Detection Works

The bot detects quiz units using the **`points` attribute** in the JSON response returned by Microsoft Learn.

* Each unit contains a `points` value.
* Units with quizzes usually have **200 points**.
* The script uses this value to determine if the unit contains questions.

### Alternative Method

Quiz units can also be detected directly from the HTML page by counting elements with:

```
div class="quiz-question"
```

If these elements exist, the unit contains quiz questions.

---

## How the Bot Solves Questions

Microsoft Learn returns the **correct answer in the response** when an answer is submitted.

The bot works by:

1. Submitting an answer to the quiz.
2. Reading the correct answer returned by the server.
3. Using that answer to complete the question automatically.

---

## Disclaimer

This project is for **educational purposes only**.
Use responsibly and ensure compliance with **Microsoft Learn terms of service**.

---

## License

MIT License
