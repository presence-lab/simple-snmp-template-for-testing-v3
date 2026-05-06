# VS Code Development Guide

This project includes VS Code configuration to enhance your development experience.

## Quick Start

1. **Open in VS Code**: Open the project folder in VS Code
2. **Install Extensions**: When prompted, install recommended extensions (or go to Extensions sidebar and search for @recommended)
3. **Select Python Interpreter**: Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac) and select "Python: Select Interpreter", then choose your virtual environment

## Features

### 🧪 Test Integration

#### Test Explorer (Sidebar)
- Click the **Testing** icon in the Activity Bar (flask icon)
- All tests appear in a tree view
- Click the play button next to any test to run it
- Green checkmark = passed, red X = failed
- Click on a failed test to jump to the failure

#### Running Tests
Several ways to run tests:

1. **Test Explorer**: Click play buttons in the Testing sidebar
2. **Command Palette** (`Ctrl+Shift+P`):
   - "Python: Run All Tests"
   - "Python: Run Test Method"
3. **Tasks** (`Ctrl+Shift+B`):
   - "Run All Tests" (default)
   - "Run Tests (Verbose)"
   - "Run Tests (Bundle 1/2/3)"
   - "Test with Coverage"
4. **Terminal**: Traditional commands still work:
   ```bash
   python run_tests.py
   pytest tests/
   ```

### 🐛 Debugging

#### Debug Configurations
Press `F5` or go to Run and Debug sidebar. Available configurations:

- **Python: Current File** - Debug the currently open Python file
- **Python: Run Tests (All)** - Debug all tests
- **Python: Run Tests (Current File)** - Debug tests in current file
- **Python: Debug Tests (Current Test)** - Debug a specific test (select test name first)
- **Python: Run Grading Script** - Debug the run_tests.py script

#### How to Debug a Test
1. Open the test file
2. Click in the gutter to set a breakpoint (red dot)
3. Select "Python: Run Tests (Current File)" from debug dropdown
4. Press `F5` to start debugging
5. Use debug controls: Continue (`F5`), Step Over (`F10`), Step Into (`F11`)

### 📝 Code Editing Features

#### IntelliSense
- **Auto-completion**: Type and get suggestions
- **Parameter hints**: See function parameters as you type
- **Quick info**: Hover over any symbol for documentation

#### Code Navigation
- **Go to Definition**: `F12` or right-click → "Go to Definition"
- **Find References**: `Shift+F12` to see all uses of a symbol
- **Outline View**: See file structure in Explorer sidebar

#### Linting
- Errors and warnings appear as:
  - Red/yellow squiggles in editor
  - Problems panel (`Ctrl+Shift+M`)
  - Inline as you type

### ⚡ Productivity Shortcuts

#### Essential Shortcuts
- `Ctrl+Shift+P`: Command Palette (all commands)
- `Ctrl+P`: Quick file open
- `Ctrl+Shift+F`: Search across all files
- `Ctrl+/`: Toggle line comment
- `Alt+Up/Down`: Move line up/down
- `Shift+Alt+Up/Down`: Copy line up/down
- `Ctrl+D`: Select next occurrence
- `F2`: Rename symbol

#### Terminal
- `` Ctrl+` ``: Toggle integrated terminal
- `Ctrl+Shift+`: Create new terminal
- Terminal automatically activates your virtual environment

### 🎯 Tasks

Access via `Terminal` → `Run Task...` or `Ctrl+Shift+B`:

- **Run All Tests**: Run grading script
- **Run Tests (Verbose)**: Detailed test output
- **Run Tests (Bundle 1/2/3)**: Test specific bundles
- **Test with Coverage**: See code coverage report
- **Copy Template to Src**: Copy starter files
- **Install Dependencies**: Install requirements.txt

### 🔧 Recommended Extensions

These extensions are recommended for this project:

1. **Python** - Core Python support
2. **Pylance** - Advanced Python language server
3. **Black Formatter** - Auto-format code
4. **Python Debugger** - Debug Python code
5. **Ruff** - Fast Python linter
6. **Even Better TOML** - TOML file support
7. **Code Spell Checker** - Catch typos

Install all at once: Open Extensions sidebar → Search "@recommended" → Install all

### 💡 Tips for Students

1. **Use the Test Explorer**: Visual feedback makes debugging easier
2. **Set Breakpoints**: Don't just print - use the debugger!
3. **Read Error Messages**: Hover over red squiggles for details
4. **Use IntelliSense**: Let VS Code help you write code
5. **Learn Shortcuts**: They'll save you tons of time

### 🚀 Workflow Example

1. Copy template files: `Ctrl+Shift+B` → "Copy Template to Src"
2. Write your code with IntelliSense help
3. Run tests from Test Explorer to see what fails
4. Set breakpoints and debug failing tests
5. Fix issues, using linting hints
6. Run all tests: `Ctrl+Shift+B` → "Run All Tests"
7. Check your grade level achieved!

### ❓ Troubleshooting

**Tests not showing in Test Explorer?**
- Make sure Python interpreter is selected
- Refresh tests: `Ctrl+Shift+P` → "Python: Refresh Tests"

**IntelliSense not working?**
- Select correct Python interpreter
- Reload window: `Ctrl+Shift+P` → "Developer: Reload Window"

**Can't debug tests?**
- Ensure virtual environment is activated
- Check that pytest is installed: `pip install -r requirements.txt`