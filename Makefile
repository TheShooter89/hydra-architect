.PHONY: install install-global uninstall test-install

install:
	./install.sh .

install-global:
	./install.sh --global

uninstall:
	./uninstall.sh .

test-install:
	rm -rf /tmp/hydra-architect-test
	mkdir -p /tmp/hydra-architect-test
	./install.sh --target /tmp/hydra-architect-test
	./uninstall.sh --force --target /tmp/hydra-architect-test
