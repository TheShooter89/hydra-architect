.PHONY: install install-global uninstall test-install

install:
	./install.sh .

install-global:
	./install.sh --global

uninstall:
	./uninstall.sh .

test-install:
	rm -rf /tmp/opencode-hydra-test
	mkdir -p /tmp/opencode-hydra-test
	./install.sh --target /tmp/opencode-hydra-test
	./uninstall.sh --force --target /tmp/opencode-hydra-test
