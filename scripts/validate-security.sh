#!/bin/bash

# Security validation script for tower-anime-production
# Checks for common security issues and misconfigurations

set -e

echo "🔒 Running Security Validation..."

# Function to print colored output
print_success() { echo -e "\033[32m✅ $1\033[0m"; }
print_warning() { echo -e "\033[33m⚠️  $1\033[0m"; }
print_error() { echo -e "\033[31m❌ $1\033[0m"; }

SECURITY_ISSUES=0

# Check for hardcoded secrets in code
echo "Checking for hardcoded secrets..."
if grep -r -i "password.*=" --include="*.py" --include="*.js" --include="*.ts" --exclude-dir=node_modules --exclude-dir=venv . | grep -v "# PASSWORD" | grep -v "DATABASE_PASSWORD.*os.getenv" ; then
    print_error "Found potential hardcoded passwords"
    SECURITY_ISSUES=$((SECURITY_ISSUES + 1))
else
    print_success "No hardcoded passwords found"
fi

# Check for API keys and tokens
if grep -r -E "(api[_-]?key|token|secret)" --include="*.py" --include="*.js" --include="*.env*" --exclude-dir=node_modules --exclude-dir=venv . | grep -v ".gitignore" | grep -v "# " | grep -v "getenv"; then
    print_warning "Found potential API keys/tokens - verify they are properly secured"
fi

# Check for database credentials
echo "Checking database credential security..."
if grep -r "postgresql://" --include="*.py" --exclude-dir=venv . | grep -v "os.getenv"; then
    print_error "Found hardcoded database URLs"
    SECURITY_ISSUES=$((SECURITY_ISSUES + 1))
else
    print_success "Database credentials properly using environment variables"
fi

# Check for CORS configuration
echo "Checking CORS configuration..."
if grep -r "allow_origins.*\[\"\*\"\]" --include="*.py" .; then
    print_error "Dangerous CORS configuration found (allow_origins=['*'])"
    SECURITY_ISSUES=$((SECURITY_ISSUES + 1))
else
    print_success "CORS configuration appears secure"
fi

# Check for debug mode in production
echo "Checking for debug configurations..."
if grep -r "debug.*=.*True" --include="*.py" .; then
    print_warning "Debug mode enabled - ensure this is disabled in production"
fi

# Check .env file is ignored
echo "Checking .env file security..."
if [ -f ".env" ] && ! grep -q "^\.env$" .gitignore; then
    print_error ".env file exists but not ignored by git"
    SECURITY_ISSUES=$((SECURITY_ISSUES + 1))
elif [ -f ".env" ]; then
    if grep -q "^[A-Z_]*=.*" .env; then
        print_warning ".env file contains variables - ensure it's not committed to git"
    fi
fi

# Check for SQL injection vulnerabilities
echo "Checking for SQL injection vulnerabilities..."
if grep -r "execute.*f\"" --include="*.py" .; then
    print_error "Potential SQL injection vulnerability found (f-string in execute)"
    SECURITY_ISSUES=$((SECURITY_ISSUES + 1))
fi

if grep -r "execute.*%" --include="*.py" . | grep -v "%s"; then
    print_warning "Check SQL string formatting for injection vulnerabilities"
fi

# Check file permissions
echo "Checking file permissions..."
if find . -name "*.py" -perm /002 2>/dev/null | head -5; then
    print_warning "Some Python files are world-writable"
fi

# Check for requirements.txt security
if [ -f "requirements.txt" ]; then
    echo "Checking Python dependencies for known vulnerabilities..."
    if command -v safety &> /dev/null; then
        safety check -r requirements.txt || print_warning "Safety check failed or found vulnerabilities"
    else
        print_warning "Safety not installed - install with 'pip install safety' for vulnerability checking"
    fi
fi

echo ""
echo "🔒 Security Validation Complete"
echo "Issues found: $SECURITY_ISSUES"

if [ $SECURITY_ISSUES -gt 0 ]; then
    print_error "Security issues detected - please fix before deployment"
    exit 1
else
    print_success "No critical security issues detected"
    exit 0
fi