# PyPI Upload Guide for Django Black Box

This guide walks you through uploading `django-blackbox` to PyPI (Python Package Index).

## Prerequisites

1. **PyPI Account**: Create accounts on both:
   - [TestPyPI](https://test.pypi.org/) (for testing)
   - [PyPI](https://pypi.org/) (production)

2. **API Token**: Generate an API token for uploads:
   - Go to Account Settings → API tokens
   - Create a token with scope: "Entire account" or "Project: django-blackbox"
   - Copy the token (starts with `pypi-`)

3. **Install Build Tools**:
   ```bash
   pip install build twine
   ```

## Step-by-Step Upload Process

### Step 1: Pre-Upload Preparation

### Update Package Metadata (Optional)

Before uploading, you may want to add more details to `pyproject.toml`:

```toml
[project]
authors = [
    { name = "Your Name", email = "your.email@example.com" },
]
readme = "README.md"
homepage = "https://github.com/yourusername/django-blackbox"
documentation = "https://github.com/yourusername/django-blackbox#readme"
repository = "https://github.com/yourusername/django-blackbox"
```

### Update Version

Ensure the version in `pyproject.toml` is correct:

```toml
[project]
version = "0.1.0"  # Update this for each release
```

Follow [Semantic Versioning](https://semver.org/):
- **MAJOR** (1.0.0): Breaking changes
- **MINOR** (0.2.0): New features (backward compatible)
- **PATCH** (0.1.1): Bug fixes

### Step 2: Clean Previous Builds

Remove any existing build artifacts:

```bash
cd /media/sarthak/Projects/python_package/django_blackbox
rm -rf dist/ build/ *.egg-info/
```

### Step 3: Build the Package

Build both source distribution and wheel:

```bash
python -m build
```

This creates:
- `dist/django-blackbox-0.1.0.tar.gz` (source distribution)
- `dist/django-blackbox-0.1.0-py3-none-any.whl` (wheel)

### Step 4: Check the Build

Verify the package contents:

```bash
twine check dist/*
```

This checks for common issues (long descriptions, invalid metadata, etc.).

### Step 5: Upload to TestPyPI (Recommended First)

Test your package on TestPyPI before uploading to production:

```bash
twine upload --repository testpypi dist/*
```

When prompted:
- **Username**: `__token__`
- **Password**: Your TestPyPI API token (starts with `pypi-`)

### Step 6: Test Installation from TestPyPI

Verify the package works correctly:

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ django-blackbox
```

Or create a fresh virtual environment:

```bash
python -m venv test_env
source test_env/bin/activate  # On Windows: test_env\Scripts\activate
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ django-blackbox
```

### Step 7: Upload to Production PyPI

Once tested, upload to the real PyPI:

```bash
twine upload dist/*
```

When prompted:
- **Username**: `__token__`
- **Password**: Your PyPI API token (different from TestPyPI token)

### Step 8: Verify Installation

Test the production installation:

```bash
pip install django-blackbox
```

## Alternative: Using Environment Variables

Instead of entering credentials each time, set environment variables:

```bash
# For TestPyPI
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-your-testpypi-token-here

# For Production PyPI
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-your-production-token-here
```

Then upload with:

```bash
twine upload dist/*
```

## Updating for Future Releases

For new versions, follow these steps:

1. **Update version** in `pyproject.toml`:
   ```toml
   version = "0.1.1"  # Increment version
   ```

2. **Update CHANGELOG** (optional but recommended):
   - Document changes, bug fixes, new features

3. **Commit and tag** in Git:
   ```bash
   git add pyproject.toml
   git commit -m "Bump version to 0.1.1"
   git tag v0.1.1
   git push origin main --tags
   ```

4. **Build and upload**:
   ```bash
   rm -rf dist/ build/ *.egg-info/
   python -m build
   twine check dist/*
   twine upload dist/*
   ```

## Quick Upload Script

Create a script `upload_to_pypi.sh` for convenience:

```bash
#!/bin/bash

set -e  # Exit on error

VERSION=$(grep '^version' pyproject.toml | sed 's/version = "\(.*\)"/\1/')

echo "Building django-blackbox version $VERSION..."

# Clean
rm -rf dist/ build/ *.egg-info/

# Build
python -m build

# Check
twine check dist/*

# Upload (change to testpypi for testing)
echo "Uploading to PyPI..."
twine upload dist/*

echo "✅ Upload complete!"
echo "Install with: pip install django-blackbox==$VERSION"
```

Make it executable:

```bash
chmod +x upload_to_pypi.sh
```

Usage:

```bash
./upload_to_pypi.sh
```

## Troubleshooting

### "File already exists" Error

PyPI doesn't allow overwriting existing versions. Solution:
1. Increment the version number in `pyproject.toml`
2. Rebuild and upload

### "Invalid Metadata" Error

Check `pyproject.toml`:
- All required fields are present
- Description is not too long
- Classifiers are valid

Run validation:

```bash
twine check dist/*
```

### Authentication Issues

- Ensure you're using `__token__` as username (not your actual username)
- Use the API token (starts with `pypi-`), not your password
- Tokens for TestPyPI and PyPI are different

### Missing Files in Package

Verify included files in `dist/*.tar.gz`:

```bash
tar -tzf dist/django-blackbox-0.1.0.tar.gz | head -20
```

Check `pyproject.toml`:
- `[tool.setuptools.packages.find]` includes all necessary packages
- `[tool.setuptools.package-data]` includes non-Python files

## Post-Upload

After successful upload:

1. **Verify on PyPI**: Visit https://pypi.org/project/django-blackbox/
2. **Update GitHub**: Add release notes on GitHub Releases page
3. **Documentation**: Update any installation docs if needed

## Additional Resources

- [PyPI Packaging Guide](https://packaging.python.org/en/latest/guides/distributing-packages-using-setuptools/)
- [Twine Documentation](https://twine.readthedocs.io/)
- [Python Packaging User Guide](https://packaging.python.org/)

## Quick Command Reference

```bash
# 1. Install build tools
pip install build twine

# 2. Clean previous builds
rm -rf dist/ build/ *.egg-info/

# 3. Build package
python -m build

# 4. Check package
twine check dist/*

# 5. Upload to TestPyPI (recommended first)
twine upload --repository testpypi dist/*

# 6. Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ django-blackbox

# 7. Upload to Production PyPI
twine upload dist/*

# 8. Verify production installation
pip install django-blackbox
```

## Your PyPI Links

Once uploaded, your package will be available at:

- **Package**: https://pypi.org/project/django-blackbox/
- **Install**: `pip install django-blackbox`
- **Documentation**: Your GitHub README will be displayed on PyPI

## Important Notes

1. **Version Numbers**: Once a version is uploaded, it cannot be overwritten. Always increment the version for new releases.

2. **TestPyPI vs PyPI**: 
   - Use TestPyPI to test your upload process
   - Use PyPI for production releases
   - They are separate - uploading to TestPyPI doesn't affect PyPI

3. **GitHub Integration**: PyPI will automatically display your README.md from the uploaded package.

---

**Good luck with your PyPI upload! 🚀**

