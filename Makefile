#
# Make file for the git-it project
#

.PHONY: tests

prefix ?= /usr/local

BIN_DIR=$(prefix)/bin
LIB_DIR=$(prefix)/lib

# files that need mode 755
EXEC_FILES=bin/it

# files that need mode 644
SCRIPT_FILES =lib/colors.py
SCRIPT_FILES+=lib/gitit.py
SCRIPT_FILES+=lib/it.py
SCRIPT_FILES+=lib/log.py
SCRIPT_FILES+=lib/misc.py
SCRIPT_FILES+=lib/ticket.py

all: archive

install:
	install -d $(BIN_DIR)
	install -d $(LIB_DIR)
	install -m 0755 $(EXEC_FILES) $(BIN_DIR)
	install -m 0644 $(SCRIPT_FILES) $(LIB_DIR)

archive:
	git archive --format=tar --prefix=git-it/ HEAD | gzip -9 > git-it.tar.gz

clean:
	find lib -type f -name '*.pyc' -exec rm {} \;
	rm -f git-it.tar.gz

tests:
	@for dir in $(PWD)/tests/*; do \
		echo === $$dir; \
		prepare_test_dir=$$(readlink -e bin/prepare-test-dir); \
		exec_it=$$(readlink -e bin/it); \
		: set -x; \
		( cd $$($$prepare_test_dir $$dir) \
		  && shelltest -w $$exec_it "$$dir" -- --hide-successes ; \
		) ; \
	done

#EOF
