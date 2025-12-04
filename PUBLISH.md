# Publishing to PyPI

This guide walks you through publishing `django-blackbox` to PyPI.

## Prerequisites

1. **PyPI Account**: You need an account on [PyPI](https://pypi.org) and [TestPyPI](https://test.pypi.org) (for testing)
2. **API Token**: Generate an API token from your PyPI account settings
   - Go to https://pypi.org/manage/account/token/
   - Create a new API token with scope "Entire account" or just for this project
   - Save the token (format: `pypi-...`)

## Step-by-Step Publishing Process

### 1. Update Version (Already Done)

The version has been updated to `0.1.1` in:
- `pyproject.toml`
- `django_blackbox/__init__.py`

To update to a different version in the future:
- For patch releases (bug fixes): `0.1.1` → `0.1.2`
- For minor releases (new features): `0.1.1` → `0.2.0`
- For major releases (breaking changes): `0.1.1` → `1.0.0`

### 2. Clean Previous Builds (Optional but Recommended)

```bash
# Remove old build artifacts
rm -rf dist/ build/ *.egg-info/
```

### 3. Install Build Tools

```bash
pip install --upgrade build twine
```

### 4. Build Distribution Packages

```bash
python -m build
```

This creates:
- `dist/django_blackbox-0.1.1-py3-none-any.whl` (wheel)
- `dist/django_blackbox-0.1.1.tar.gz` (source distribution)

### 5. Test on TestPyPI (Recommended)

Before publishing to production PyPI, test on TestPyPI:

```bash
# Upload to TestPyPI
python -m twine upload --repository testpypi dist/*

# You'll be prompted for:
# - Username: __token__
# - Password: your TestPyPI API token (pypi-...)
```

Then test installation:
```bash
pip install --index-url https://test.pypi.org/simple/ django-blackbox==0.1.1
```

### 6. Upload to Production PyPI

Once tested, upload to production PyPI:

```bash
python -m twine upload dist/*
```

You'll be prompted for:
- **Username**: `__token__`
- **Password**: Your PyPI API token (starts with `pypi-...`)

### 7. Verify Installation

After a few minutes, verify the package is available:

```bash
pip install django-blackbox==0.1.1
```

## Quick Command Reference

```bash
# Full publishing workflow
rm -rf dist/ build/ *.egg-info/
python -m build
python -m twine upload dist/*
```

## Troubleshooting

### "File already exists" Error

If you get an error that the version already exists on PyPI:
1. You need to bump the version number
2. PyPI doesn't allow overwriting existing versions

### Authentication Issues

- Make sure you're using `__token__` as the username
- Use your API token (not your password)
- Ensure the token has the correct scope

### Build Errors

- Make sure `pyproject.toml` is valid
- Check that all required fields are present
- Verify Python version compatibility

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):
- **MAJOR.MINOR.PATCH** (e.g., `1.2.3`)
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

## Next Steps After Publishing

1. **Tag the Release in Git**:
   ```bash
   git tag v0.1.1
   git push origin v0.1.1
   ```

2. **Create a GitHub Release** (optional):
   - Go to your GitHub repository
   - Create a new release with tag `v0.1.1`
   - Add release notes describing the changes

3. **Update Documentation** (if needed):
   - Update README if there are breaking changes
   - Update changelog if you maintain one


