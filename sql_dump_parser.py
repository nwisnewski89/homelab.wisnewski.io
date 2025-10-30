#!/usr/bin/env python3
"""
SQL Dump Parser for Drupal CMS Content

This script parses SQL dump files containing upsert statements where semicolons
may appear inside string values. It properly handles quoted strings to avoid
splitting statements incorrectly.

Usage:
    python sql_dump_parser.py <dump_file.sql>
    python sql_dump_parser.py <dump_file.sql> --output statements.txt
    python sql_dump_parser.py <dump_file.sql> --count-only
"""

import argparse
import re
import sys
from typing import List, Iterator, Optional
import os


class SQLDumpParser:
    """
    Parser for SQL dump files that handles semicolons within quoted strings.
    
    This parser correctly identifies statement boundaries by tracking
    quote states and escape sequences.
    """
    
    def __init__(self):
        # Quote characters that can be used in SQL
        self.quote_chars = ["'", '"', '`']
        # Escape character
        self.escape_char = '\\'
    
    def parse_statements(self, sql_content: str) -> List[str]:
        """
        Parse SQL content and return individual statements.
        
        Args:
            sql_content: The SQL dump content as a string
            
        Returns:
            List of individual SQL statements
        """
        statements = []
        current_statement = ""
        in_quoted_string = False
        current_quote = None
        i = 0
        
        while i < len(sql_content):
            char = sql_content[i]
            
            if not in_quoted_string:
                # Check if we're entering a quoted string
                if char in self.quote_chars:
                    in_quoted_string = True
                    current_quote = char
                    current_statement += char
                elif char == ';':
                    # End of statement
                    if current_statement.strip():
                        statements.append(current_statement.strip())
                    current_statement = ""
                else:
                    current_statement += char
            else:
                # We're inside a quoted string
                if char == self.escape_char:
                    # Check if next character is the quote or escape
                    if i + 1 < len(sql_content):
                        next_char = sql_content[i + 1]
                        if next_char == current_quote or next_char == self.escape_char:
                            # Escaped quote or escape character
                            current_statement += char + next_char
                            i += 1  # Skip the next character
                        else:
                            # Regular escape character
                            current_statement += char
                    else:
                        # Escape at end of string
                        current_statement += char
                elif char == current_quote:
                    # End of quoted string
                    in_quoted_string = False
                    current_quote = None
                    current_statement += char
                else:
                    # Regular character inside quoted string
                    current_statement += char
            
            i += 1
        
        # Add the last statement if it exists and doesn't end with semicolon
        if current_statement.strip():
            statements.append(current_statement.strip())
        
        return statements
    
    def parse_file(self, file_path: str) -> List[str]:
        """
        Parse a SQL dump file and return individual statements.
        
        Args:
            file_path: Path to the SQL dump file
            
        Returns:
            List of individual SQL statements
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.parse_statements(content)
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
                return self.parse_statements(content)
            except Exception as e:
                raise Exception(f"Could not read file {file_path}: {e}")
        except Exception as e:
            raise Exception(f"Error reading file {file_path}: {e}")
    
    def validate_statements(self, statements: List[str]) -> List[dict]:
        """
        Validate parsed statements and return analysis.
        
        Args:
            statements: List of SQL statements
            
        Returns:
            List of dictionaries with validation info
        """
        results = []
        
        for i, statement in enumerate(statements):
            result = {
                'index': i + 1,
                'statement': statement,
                'length': len(statement),
                'is_empty': not statement.strip(),
                'starts_with_upsert': statement.strip().upper().startswith(('INSERT', 'UPDATE', 'REPLACE')),
                'has_semicolon': ';' in statement,
                'quote_count_single': statement.count("'"),
                'quote_count_double': statement.count('"'),
                'quote_count_backtick': statement.count('`')
            }
            results.append(result)
        
        return results


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(
        description='Parse SQL dump files with proper handling of semicolons in quoted strings',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sql_dump_parser.py dump.sql
  python sql_dump_parser.py dump.sql --output statements.txt
  python sql_dump_parser.py dump.sql --count-only
  python sql_dump_parser.py dump.sql --validate
        """
    )
    
    parser.add_argument('file', help='SQL dump file to parse')
    parser.add_argument('--output', '-o', help='Output file for statements')
    parser.add_argument('--count-only', action='store_true', 
                       help='Only show count of statements')
    parser.add_argument('--validate', action='store_true',
                       help='Show validation analysis')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed output')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"Error: File '{args.file}' not found", file=sys.stderr)
        sys.exit(1)
    
    try:
        sql_parser = SQLDumpParser()
        statements = sql_parser.parse_file(args.file)
        
        if args.count_only:
            print(f"Found {len(statements)} SQL statements")
            return
        
        if args.validate:
            validation_results = sql_parser.validate_statements(statements)
            
            print(f"Validation Results for {len(statements)} statements:")
            print("=" * 60)
            
            empty_count = sum(1 for r in validation_results if r['is_empty'])
            upsert_count = sum(1 for r in validation_results if r['starts_with_upsert'])
            semicolon_count = sum(1 for r in validation_results if r['has_semicolon'])
            
            print(f"Total statements: {len(statements)}")
            print(f"Empty statements: {empty_count}")
            print(f"Upsert statements: {upsert_count}")
            print(f"Statements with semicolons: {semicolon_count}")
            
            if args.verbose:
                print("\nDetailed Analysis:")
                print("-" * 60)
                for result in validation_results[:10]:  # Show first 10
                    print(f"Statement {result['index']}:")
                    print(f"  Length: {result['length']} chars")
                    print(f"  Empty: {result['is_empty']}")
                    print(f"  Upsert: {result['starts_with_upsert']}")
                    print(f"  Has semicolon: {result['has_semicolon']}")
                    print(f"  Quotes: single={result['quote_count_single']}, "
                          f"double={result['quote_count_double']}, "
                          f"backtick={result['quote_count_backtick']}")
                    if result['statement']:
                        preview = result['statement'][:100] + "..." if len(result['statement']) > 100 else result['statement']
                        print(f"  Preview: {preview}")
                    print()
                
                if len(validation_results) > 10:
                    print(f"... and {len(validation_results) - 10} more statements")
            
            return
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                for i, statement in enumerate(statements, 1):
                    f.write(f"-- Statement {i}\n")
                    f.write(f"{statement};\n\n")
            print(f"Wrote {len(statements)} statements to {args.output}")
        else:
            # Print to stdout
            for i, statement in enumerate(statements, 1):
                if args.verbose:
                    print(f"-- Statement {i}")
                print(statement)
                if not statement.endswith(';'):
                    print(';')
                print()
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
