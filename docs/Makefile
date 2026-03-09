# Makefile to compile Markdown documents to PDF using pandoc and groff

MD_FILES = project_plan.md database_schema.md
PDF_FILES = $(MD_FILES:.md=.pdf)

.PHONY: all clean

all: $(PDF_FILES)

# Uses pandoc with --pdf-engine to convert Markdown to PDF using ms macros
%.pdf: %.md
	pandoc $< -o $@ -t ms --pdf-engine=pdfroff

clean:
	rm -f $(PDF_FILES)
