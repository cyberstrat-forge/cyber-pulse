# Makefile for cyber-pulse
#
# Usage:
#   make verify          # 运行验证系统
#   make verify-report   # 验证并生成报告

.PHONY: verify verify-report help

# 验证系统
verify:
	@echo "开始验证 cyber-pulse..."
	@./scripts/verify.sh

# 验证并保存报告
verify-report:
	@echo "验证并生成报告..."
	@mkdir -p logs
	@./scripts/verify.sh --output logs/verify-report.md

# 帮助
help:
	@echo "cyber-pulse Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  verify         运行验证系统"
	@echo "  verify-report  验证并生成报告到 logs/verify-report.md"
	@echo "  help           显示此帮助信息"
