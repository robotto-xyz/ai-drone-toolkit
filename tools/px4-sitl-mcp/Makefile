.PHONY: sim test check

sim:
	@echo "Start PX4 SITL separately, for example:"
	@echo "  cd /path/to/PX4-Autopilot && make px4_sitl gz_x500"
	@echo ""
	@echo "Then run this MCP server from the ai-drone-toolkit root:"
	@echo "  uv run px4-sitl-mcp"

test:
	uv run pytest tools/px4-sitl-mcp

check: test
