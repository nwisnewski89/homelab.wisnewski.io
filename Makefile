# Example Makefile showing different ways to chain commands

# Method 1: Multiple commands on the same line with semicolons
target1:
	@echo "Starting target1"
	@echo "Command 1"; echo "Command 2"; echo "Command 3"
	@echo "Finished target1"

# Method 2: Multiple commands on separate lines (each line runs in separate shell)
target2:
	@echo "Starting target2"
	@echo "Command 1"
	@echo "Command 2"
	@echo "Command 3"
	@echo "Finished target2"

# Method 3: Using && to chain commands (stops on first failure)
target3:
	@echo "Starting target3" && \
	echo "Command 1" && \
	echo "Command 2" && \
	echo "Command 3" && \
	echo "Finished target3"

# Method 4: Using ; to chain commands (continues even if one fails)
target4:
	@echo "Starting target4"; \
	echo "Command 1"; \
	echo "Command 2"; \
	echo "Command 3"; \
	echo "Finished target4"

# Method 5: Using backslashes for multi-line commands
target5:
	@echo "Starting target5" && \
		echo "Command 1" && \
		echo "Command 2" && \
		echo "Command 3" && \
		echo "Finished target5"

# Method 6: Chaining with conditional execution
target6:
	@echo "Starting target6" && \
	if [ -f "test.txt" ]; then \
		echo "File exists, deleting it"; \
		rm test.txt; \
	else \
		echo "File does not exist"; \
	fi && \
	echo "Finished target6"

# Method 7: Using make dependencies to chain targets
setup:
	@echo "Setting up environment"
	@mkdir -p build
	@touch build/.setup-complete

build: setup
	@echo "Building project"
	@echo "Build complete" > build/output.txt

test: build
	@echo "Running tests"
	@echo "Tests passed" >> build/output.txt

deploy: test
	@echo "Deploying application"
	@echo "Deployment complete" >> build/output.txt

# Method 8: Using .ONESHELL directive for better shell integration
.ONESHELL:
target8:
	@echo "Starting target8"
	@set -e  # Exit on any error
	@echo "Command 1"
	@echo "Command 2"
	@echo "Command 3"
	@echo "Finished target8"

# Method 9: Chaining with environment variables
target9:
	@export COUNTER=0 && \
	echo "Counter: $$COUNTER" && \
	export COUNTER=$$((COUNTER + 1)) && \
	echo "Counter: $$COUNTER" && \
	export COUNTER=$$((COUNTER + 1)) && \
	echo "Counter: $$COUNTER"

# Method 10: Using functions and chaining
define cleanup
	@echo "Cleaning up..."
	@rm -f *.tmp
	@rm -f *.log
	@echo "Cleanup complete"
endef

clean: 
	$(cleanup)

# Method 11: Chaining with error handling
target11:
	@echo "Starting target11" && \
	{ \
		echo "Command 1" && \
		echo "Command 2" && \
		echo "Command 3"; \
	} || { \
		echo "Error occurred"; \
		exit 1; \
	} && \
	echo "Finished target11"

# Method 12: Using make's built-in functions
target12:
	@echo "Starting target12"
	@$(shell echo "Command 1")
	@$(shell echo "Command 2")
	@$(shell echo "Command 3")
	@echo "Finished target12"

# Method 13: Chaining with file operations
target13:
	@echo "Creating files..." && \
	echo "content1" > file1.txt && \
	echo "content2" > file2.txt && \
	echo "content3" > file3.txt && \
	echo "Files created successfully"

# Method 14: Using loops in chained commands
target14:
	@echo "Starting loop" && \
	for i in 1 2 3 4 5; do \
		echo "Iteration $$i"; \
	done && \
	echo "Loop finished"

# Method 15: Chaining with conditional compilation
DEBUG ?= false

target15:
	@echo "Starting target15" && \
	if [ "$(DEBUG)" = "true" ]; then \
		echo "Debug mode enabled"; \
		echo "Running debug commands..."; \
	else \
		echo "Production mode"; \
		echo "Running production commands..."; \
	fi && \
	echo "Finished target15"

# Method 16: Using make's parallel execution with dependencies
.PHONY: parallel1 parallel2 parallel3

parallel1:
	@echo "Task 1 starting"
	@sleep 2
	@echo "Task 1 complete"

parallel2:
	@echo "Task 2 starting"
	@sleep 2
	@echo "Task 2 complete"

parallel3:
	@echo "Task 3 starting"
	@sleep 2
	@echo "Task 3 complete"

parallel-all: parallel1 parallel2 parallel3
	@echo "All parallel tasks completed"

# Method 17: Chaining with make variables
VERSION := 1.0.0
BUILD_DIR := build

target17:
	@echo "Building version $(VERSION)" && \
	mkdir -p $(BUILD_DIR) && \
	echo "Version: $(VERSION)" > $(BUILD_DIR)/version.txt && \
	echo "Build complete in $(BUILD_DIR)"

# Method 18: Using make's include directive to chain makefiles
# include other.mk

# Method 19: Chaining with command substitution
target19:
	@echo "Current directory: $(shell pwd)" && \
	echo "Files in directory: $(shell ls -la)" && \
	echo "Command substitution complete"

# Method 20: Using make's eval function for dynamic chaining
target20:
	@echo "Dynamic command chaining" && \
	$(eval CMD1 := echo "Dynamic command 1") && \
	$(eval CMD2 := echo "Dynamic command 2") && \
	$(eval CMD3 := echo "Dynamic command 3") && \
	$(CMD1) && \
	$(CMD2) && \
	$(CMD3) && \
	echo "Dynamic chaining complete"

# ========================================
# VARIABLE PASSING BETWEEN MAKE STAGES
# ========================================

# Method 21: Using make variables (global scope)
BUILD_VERSION := 1.0.0
BUILD_DIR := build
SOURCE_DIR := src

stage1:
	@echo "Stage 1: Building version $(BUILD_VERSION)"
	@mkdir -p $(BUILD_DIR)
	@echo "Build directory: $(BUILD_DIR)"

stage2: stage1
	@echo "Stage 2: Using version $(BUILD_VERSION) from stage1"
	@echo "Source directory: $(SOURCE_DIR)"
	@echo "Build directory: $(BUILD_DIR)"

stage3: stage2
	@echo "Stage 3: Final stage with version $(BUILD_VERSION)"
	@echo "All variables available: BUILD_VERSION=$(BUILD_VERSION), BUILD_DIR=$(BUILD_DIR), SOURCE_DIR=$(SOURCE_DIR)"

# Method 22: Using target-specific variables
stage4:
	@echo "Stage 4: Setting target-specific variable"
	$(eval STAGE4_VAR := "Hello from stage4")

stage5: stage4
	@echo "Stage 5: Cannot access STAGE4_VAR directly: $(STAGE4_VAR)"
	@echo "Target-specific variables are not shared between targets"

# Method 23: Using file-based variable passing
stage6:
	@echo "Stage 6: Writing variables to file"
	@echo "VERSION=2.0.0" > build/vars.txt
	@echo "TIMESTAMP=$(shell date)" >> build/vars.txt
	@echo "USER=$(shell whoami)" >> build/vars.txt

stage7: stage6
	@echo "Stage 7: Reading variables from file"
	@source build/vars.txt && echo "VERSION: $$VERSION"
	@source build/vars.txt && echo "TIMESTAMP: $$TIMESTAMP"
	@source build/vars.txt && echo "USER: $$USER"

# Method 24: Using environment variables
stage8:
	@echo "Stage 8: Setting environment variables"
	@export STAGE8_VAR="Environment variable from stage8"
	@export STAGE8_NUMBER=42
	@echo "Variables set in stage8"

stage9: stage8
	@echo "Stage 9: Environment variables are not preserved between targets"
	@echo "STAGE8_VAR: $$STAGE8_VAR"
	@echo "STAGE8_NUMBER: $$STAGE8_NUMBER"

# Method 25: Using .ONESHELL with variables
.ONESHELL:
stage10:
	@echo "Stage 10: Using .ONESHELL for variable persistence"
	@export SHELL_VAR="Persistent shell variable"
	@export SHELL_NUMBER=100
	@echo "Shell variables set: SHELL_VAR=$$SHELL_VAR, SHELL_NUMBER=$$SHELL_NUMBER"

stage11: stage10
	@echo "Stage 11: .ONESHELL variables are not shared between targets"
	@echo "SHELL_VAR: $$SHELL_VAR"
	@echo "SHELL_NUMBER: $$SHELL_NUMBER"

# Method 26: Using make's eval and call functions
define set_variable
	$(eval $(1) := $(2))
endef

define get_variable
	$(value $(1))
endef

stage12:
	@echo "Stage 12: Using eval to set global variables"
	$(call set_variable,GLOBAL_VAR,Hello from stage12)
	$(call set_variable,GLOBAL_NUMBER,999)
	@echo "Global variables set"

stage13: stage12
	@echo "Stage 13: Accessing global variables set in stage12"
	@echo "GLOBAL_VAR: $(call get_variable,GLOBAL_VAR)"
	@echo "GLOBAL_NUMBER: $(call get_variable,GLOBAL_NUMBER)"

# Method 27: Using make's export directive
stage14:
	@echo "Stage 14: Using export directive"
	@export EXPORTED_VAR="Exported variable"
	@export EXPORTED_NUMBER=123
	@echo "Variables exported"

stage15: stage14
	@echo "Stage 15: Exported variables are not preserved between targets"
	@echo "EXPORTED_VAR: $$EXPORTED_VAR"
	@echo "EXPORTED_NUMBER: $$EXPORTED_NUMBER"

# Method 28: Using command substitution and file passing
stage16:
	@echo "Stage 16: Using command substitution"
	@echo "$$(date)" > build/timestamp.txt
	@echo "$$(whoami)" > build/user.txt
	@echo "$$(pwd)" > build/pwd.txt

stage17: stage16
	@echo "Stage 17: Reading from command substitution files"
	@echo "Timestamp: $$(cat build/timestamp.txt)"
	@echo "User: $$(cat build/user.txt)"
	@echo "PWD: $$(cat build/pwd.txt)"

# Method 29: Using make's include directive for shared variables
# Create a separate file: shared-vars.mk
# VERSION := 3.0.0
# BUILD_TYPE := release
# include shared-vars.mk

stage18:
	@echo "Stage 18: Using included variables"
	@echo "VERSION: $(VERSION)"
	@echo "BUILD_TYPE: $(BUILD_TYPE)"

# Method 30: Using make's override directive
stage19:
	@echo "Stage 19: Using override directive"
	$(eval override OVERRIDE_VAR := "Overridden value")
	@echo "OVERRIDE_VAR: $(OVERRIDE_VAR)"

stage20: stage19
	@echo "Stage 20: Override variables are global"
	@echo "OVERRIDE_VAR: $(OVERRIDE_VAR)"

# Method 31: Using make's call function with parameters
define process_stage
	@echo "Processing stage: $(1)"
	@echo "With parameter: $(2)"
	@echo "And another: $(3)"
endef

stage21:
	$(call process_stage,Stage21,Parameter1,Parameter2)

stage22: stage21
	$(call process_stage,Stage22,ParamA,ParamB)

# Method 32: Using make's foreach with variables
stage23:
	@echo "Stage 23: Using foreach with variables"
	$(foreach item,apple banana cherry,$(eval $(item)_COUNT := 0))
	@echo "Variables set for: apple, banana, cherry"

stage24: stage23
	@echo "Stage 24: Accessing foreach variables"
	@echo "apple_COUNT: $(apple_COUNT)"
	@echo "banana_COUNT: $(banana_COUNT)"
	@echo "cherry_COUNT: $(cherry_COUNT)"

# Method 33: Using make's shell function for dynamic variables
stage25:
	@echo "Stage 25: Using shell function for dynamic variables"
	$(eval DYNAMIC_VAR := $(shell echo "Dynamic value from shell"))
	$(eval RANDOM_NUMBER := $(shell echo $$RANDOM))
	@echo "DYNAMIC_VAR: $(DYNAMIC_VAR)"
	@echo "RANDOM_NUMBER: $(RANDOM_NUMBER)"

stage26: stage25
	@echo "Stage 26: Shell function variables are global"
	@echo "DYNAMIC_VAR: $(DYNAMIC_VAR)"
	@echo "RANDOM_NUMBER: $(RANDOM_NUMBER)"

# Method 34: Using make's define with variable expansion
define stage_function
	@echo "Stage function called with: $(1)"
	@echo "Current VERSION: $(VERSION)"
	@echo "Current BUILD_DIR: $(BUILD_DIR)"
endef

stage27:
	$(call stage_function,Stage27)

stage28: stage27
	$(call stage_function,Stage28)

# Method 35: Using make's ifdef for conditional variable passing
stage29:
	@echo "Stage 29: Setting conditional variables"
	$(if $(filter debug,$(MAKECMDGOALS)),$(eval DEBUG_MODE := true),$(eval DEBUG_MODE := false))
	@echo "DEBUG_MODE: $(DEBUG_MODE)"

stage30: stage29
	@echo "Stage 30: Using conditional variables"
	@echo "DEBUG_MODE: $(DEBUG_MODE)"
	@if [ "$(DEBUG_MODE)" = "true" ]; then \
		echo "Debug mode enabled"; \
	else \
		echo "Debug mode disabled"; \
	fi

# ========================================
# ENVIRONMENT VARIABLE ACCESS IN MAKE
# ========================================

# Method 36: Accessing shell environment variables
env-test:
	@echo "=== Environment Variable Access ==="
	@echo "HOME: $(HOME)"
	@echo "USER: $(USER)"
	@echo "PATH: $(PATH)"
	@echo "PWD: $(PWD)"
	@echo "SHELL: $(SHELL)"

# Method 37: Accessing custom environment variables
env-custom:
	@echo "=== Custom Environment Variables ==="
	@echo "CUSTOM_VAR: $(CUSTOM_VAR)"
	@echo "BUILD_ENV: $(BUILD_ENV)"
	@echo "API_KEY: $(API_KEY)"
	@echo "DEBUG: $(DEBUG)"

# Method 38: Using environment variables with defaults
env-with-defaults:
	@echo "=== Environment Variables with Defaults ==="
	@echo "BUILD_TYPE: $(BUILD_TYPE)"
	@echo "VERSION: $(VERSION)"
	@echo "PORT: $(PORT)"
	@echo "HOST: $(HOST)"

# Method 39: Conditional logic based on environment variables
env-conditional:
	@echo "=== Conditional Logic Based on Environment ==="
	@if [ "$(CI)" = "true" ]; then \
		echo "Running in CI environment"; \
		echo "CI_COMMIT_SHA: $(CI_COMMIT_SHA)"; \
		echo "CI_COMMIT_BRANCH: $(CI_COMMIT_BRANCH)"; \
	else \
		echo "Running in local environment"; \
	fi
	@if [ "$(DEBUG)" = "true" ]; then \
		echo "Debug mode enabled"; \
	else \
		echo "Debug mode disabled"; \
	fi

# Method 40: Using environment variables in make variables
env-in-make-vars:
	@echo "=== Environment Variables in Make Variables ==="
	$(eval BUILD_VERSION := $(VERSION))
	$(eval BUILD_USER := $(USER))
	$(eval BUILD_HOST := $(HOSTNAME))
	@echo "BUILD_VERSION: $(BUILD_VERSION)"
	@echo "BUILD_USER: $(BUILD_USER)"
	@echo "BUILD_HOST: $(BUILD_HOST)"

# Method 41: Exporting make variables to environment
env-export:
	@echo "=== Exporting Make Variables ==="
	@export MAKE_VAR="Hello from Make"
	@export MAKE_VERSION="1.0.0"
	@echo "MAKE_VAR: $$MAKE_VAR"
	@echo "MAKE_VERSION: $$MAKE_VERSION"

# Method 42: Using environment variables in file operations
env-file-ops:
	@echo "=== Environment Variables in File Operations ==="
	@echo "Build by: $(USER)" > build/build-info.txt
	@echo "Build time: $(shell date)" >> build/build-info.txt
	@echo "Build host: $(HOSTNAME)" >> build/build-info.txt
	@echo "Build path: $(PWD)" >> build/build-info.txt
	@cat build/build-info.txt

# Method 43: Environment variables in shell commands
env-shell-cmds:
	@echo "=== Environment Variables in Shell Commands ==="
	@echo "Current user: $$USER"
	@echo "Current directory: $$PWD"
	@echo "Shell: $$SHELL"
	@echo "Home directory: $$HOME"

# Method 44: Using environment variables with make's export directive
env-export-directive:
	@echo "=== Export Directive ==="
	@export EXPORTED_VAR="This is exported"
	@echo "EXPORTED_VAR: $$EXPORTED_VAR"

# Method 45: Environment variables in dependency chains
env-dependency:
	@echo "=== Environment Variables in Dependencies ==="
	@echo "Building for user: $(USER)"
	@echo "On host: $(HOSTNAME)"
	@echo "In directory: $(PWD)"

env-build: env-dependency
	@echo "=== Build Stage ==="
	@echo "Build environment: $(BUILD_ENV)"
	@echo "Build type: $(BUILD_TYPE)"

env-test-chain: env-build
	@echo "=== Test Stage ==="
	@echo "Test environment: $(TEST_ENV)"
	@echo "Test user: $(USER)"

# Method 46: Using environment variables with make's override
env-override:
	@echo "=== Override with Environment Variables ==="
	$(eval override ENV_OVERRIDE := $(ENV_VAR))
	@echo "ENV_OVERRIDE: $(ENV_OVERRIDE)"
	@echo "Original ENV_VAR: $(ENV_VAR)"

# Method 47: Environment variables in make functions
define env_function
	@echo "Function called by: $(USER)"
	@echo "On host: $(HOSTNAME)"
	@echo "With parameter: $(1)"
endef

env-func-test:
	$(call env_function,Test Parameter)

# Method 48: Using environment variables for conditional compilation
env-conditional-compile:
	@echo "=== Conditional Compilation ==="
	@if [ "$(BUILD_TYPE)" = "debug" ]; then \
		echo "Compiling in debug mode"; \
		echo "Debug flags: -g -O0"; \
	elif [ "$(BUILD_TYPE)" = "release" ]; then \
		echo "Compiling in release mode"; \
		echo "Release flags: -O2 -DNDEBUG"; \
	else \
		echo "Compiling in default mode"; \
	fi

# Method 49: Environment variables in parallel execution
env-parallel:
	@echo "=== Parallel Execution with Environment ==="
	@echo "Parallel job 1 - User: $(USER)" &
	@echo "Parallel job 2 - Host: $(HOSTNAME)" &
	@echo "Parallel job 3 - PWD: $(PWD)" &
	@wait

# Method 50: Using environment variables for dynamic target names
env-dynamic-target:
	@echo "=== Dynamic Target Names ==="
	@echo "Target for user: $(USER)"
	@echo "Target for environment: $(BUILD_ENV)"
	@echo "Target for build type: $(BUILD_TYPE)"

# ========================================
# PARALLEL EXECUTION IN MAKE
# ========================================

# Method 51: Basic parallel execution with dependencies
parallel-task1:
	@echo "Task 1 starting at $$(date)"
	@sleep 3
	@echo "Task 1 complete at $$(date)"

parallel-task2:
	@echo "Task 2 starting at $$(date)"
	@sleep 2
	@echo "Task 2 complete at $$(date)"

parallel-task3:
	@echo "Task 3 starting at $$(date)"
	@sleep 4
	@echo "Task 3 complete at $$(date)"

# All tasks run in parallel
parallel-all-tasks: parallel-task1 parallel-task2 parallel-task3
	@echo "All parallel tasks completed at $$(date)"

# Method 52: Parallel execution with job limits
parallel-limited: parallel-task1 parallel-task2 parallel-task3
	@echo "Limited parallel tasks completed"

# Method 53: Parallel execution with shell commands
parallel-shell:
	@echo "Starting parallel shell commands at $$(date)"
	@(echo "Shell job 1 starting"; sleep 3; echo "Shell job 1 complete") &
	@(echo "Shell job 2 starting"; sleep 2; echo "Shell job 2 complete") &
	@(echo "Shell job 3 starting"; sleep 4; echo "Shell job 3 complete") &
	@wait
	@echo "All shell jobs completed at $$(date)"

# Method 54: Parallel execution with background processes
parallel-background:
	@echo "Starting background processes"
	@echo "Background job 1" > /tmp/job1.log 2>&1 &
	@echo "Background job 2" > /tmp/job2.log 2>&1 &
	@echo "Background job 3" > /tmp/job3.log 2>&1 &
	@sleep 2
	@echo "Job 1 output: $$(cat /tmp/job1.log)"
	@echo "Job 2 output: $$(cat /tmp/job2.log)"
	@echo "Job 3 output: $$(cat /tmp/job3.log)"

# Method 55: Parallel execution with make's -j flag simulation
parallel-jobs:
	@echo "Simulating make -j4 behavior"
	@for i in 1 2 3 4; do \
		(echo "Job $$i starting"; sleep $$((RANDOM % 5 + 1)); echo "Job $$i complete") & \
	done
	@wait
	@echo "All jobs completed"

# Method 56: Parallel execution with dependency groups
parallel-group1:
	@echo "Group 1 task 1"
	@sleep 2

parallel-group2:
	@echo "Group 2 task 1"
	@sleep 2

parallel-group3:
	@echo "Group 3 task 1"
	@sleep 2

# Groups run in parallel, but tasks within groups run sequentially
parallel-groups: parallel-group1 parallel-group2 parallel-group3
	@echo "All groups completed"

# Method 57: Parallel execution with conditional tasks
parallel-conditional:
	@echo "Starting conditional parallel tasks"
	@if [ "$(BUILD_TYPE)" = "debug" ]; then \
		(echo "Debug build starting"; sleep 2; echo "Debug build complete") & \
	fi
	@if [ "$(BUILD_TYPE)" = "release" ]; then \
		(echo "Release build starting"; sleep 3; echo "Release build complete") & \
	fi
	@(echo "Common task starting"; sleep 1; echo "Common task complete") &
	@wait
	@echo "Conditional parallel tasks completed"

# Method 58: Parallel execution with make's .NOTPARALLEL directive
.NOTPARALLEL: sequential-task1 sequential-task2 sequential-task3

sequential-task1:
	@echo "Sequential task 1 starting at $$(date)"
	@sleep 2
	@echo "Sequential task 1 complete at $$(date)"

sequential-task2:
	@echo "Sequential task 2 starting at $$(date)"
	@sleep 2
	@echo "Sequential task 2 complete at $$(date)"

sequential-task3:
	@echo "Sequential task 3 starting at $$(date)"
	@sleep 2
	@echo "Sequential task 3 complete at $$(date)"

sequential-all: sequential-task1 sequential-task2 sequential-task3
	@echo "All sequential tasks completed at $$(date)"

# Method 59: Parallel execution with resource limits
parallel-resource-limited:
	@echo "Starting resource-limited parallel tasks"
	@# Limit to 2 concurrent processes
	@(echo "Resource job 1"; sleep 3) &
	@(echo "Resource job 2"; sleep 3) &
	@wait
	@(echo "Resource job 3"; sleep 3) &
	@(echo "Resource job 4"; sleep 3) &
	@wait
	@echo "Resource-limited tasks completed"

# Method 60: Parallel execution with make's .SECONDEXPANSION
.SECONDEXPANSION:
parallel-second-expansion: $$(addprefix parallel-job-,1 2 3 4)
	@echo "Second expansion parallel tasks completed"

parallel-job-%:
	@echo "Second expansion job $$* starting"
	@sleep $$((RANDOM % 3 + 1))
	@echo "Second expansion job $$* complete"

# Method 61: Parallel execution with dynamic task generation
parallel-dynamic:
	@echo "Starting dynamic parallel tasks"
	@for task in task1 task2 task3 task4; do \
		(echo "Dynamic $$task starting"; sleep $$((RANDOM % 4 + 1)); echo "Dynamic $$task complete") & \
	done
	@wait
	@echo "Dynamic parallel tasks completed"

# Method 62: Parallel execution with make's .PHONY directive
.PHONY: parallel-phony1 parallel-phony2 parallel-phony3

parallel-phony1:
	@echo "Phony task 1 starting"
	@sleep 2
	@echo "Phony task 1 complete"

parallel-phony2:
	@echo "Phony task 2 starting"
	@sleep 2
	@echo "Phony task 2 complete"

parallel-phony3:
	@echo "Phony task 3 starting"
	@sleep 2
	@echo "Phony task 3 complete"

parallel-phony: parallel-phony1 parallel-phony2 parallel-phony3
	@echo "All phony tasks completed"

# Method 63: Parallel execution with error handling
parallel-error-handling:
	@echo "Starting parallel tasks with error handling"
	@(echo "Task 1"; sleep 2; echo "Task 1 success") &
	@(echo "Task 2"; sleep 1; echo "Task 2 success") &
	@(echo "Task 3"; sleep 3; echo "Task 3 success") &
	@wait
	@echo "All tasks completed successfully"

# Method 64: Parallel execution with make's .INTERMEDIATE directive
parallel-intermediate: intermediate-file1 intermediate-file2 intermediate-file3
	@echo "Intermediate files created in parallel"

intermediate-file1:
	@echo "Creating intermediate file 1"
	@echo "content1" > $@
	@sleep 2

intermediate-file2:
	@echo "Creating intermediate file 2"
	@echo "content2" > $@
	@sleep 2

intermediate-file3:
	@echo "Creating intermediate file 3"
	@echo "content3" > $@
	@sleep 2

# Method 65: Parallel execution with make's .PRECIOUS directive
parallel-precious: precious-file1 precious-file2 precious-file3
	@echo "Precious files created in parallel"

precious-file1:
	@echo "Creating precious file 1"
	@echo "precious1" > $@
	@sleep 2

precious-file2:
	@echo "Creating precious file 2"
	@echo "precious2" > $@
	@sleep 2

precious-file3:
	@echo "Creating precious file 3"
	@echo "precious3" > $@
	@sleep 2

.PRECIOUS: precious-file1 precious-file2 precious-file3

# ========================================
# COMBINING TASKS IN MAKE
# ========================================

# Method 66: Simple task combination with dependencies
task1:
	@echo "Task 1 executing"
	@echo "Task 1 complete"

task2:
	@echo "Task 2 executing"
	@echo "Task 2 complete"

# Combine tasks using dependencies
combined-tasks: task1 task2
	@echo "Both tasks completed"

# Method 67: Combining tasks with a single target
combined-single:
	@echo "=== Combined Task Execution ==="
	@echo "Executing task 1..."
	@echo "Task 1 logic here"
	@echo "Task 1 complete"
	@echo "Executing task 2..."
	@echo "Task 2 logic here"
	@echo "Task 2 complete"
	@echo "=== Combined execution finished ==="

# Method 68: Combining tasks with shell chaining
combined-shell:
	@echo "=== Shell Combined Tasks ==="
	@echo "Task 1 starting" && \
	echo "Task 1 executing..." && \
	echo "Task 1 complete" && \
	echo "Task 2 starting" && \
	echo "Task 2 executing..." && \
	echo "Task 2 complete" && \
	echo "=== Shell combined execution finished ==="

# Method 69: Combining tasks with error handling
combined-error-handling:
	@echo "=== Error Handling Combined Tasks ==="
	@(echo "Task 1 starting"; \
	  echo "Task 1 executing..."; \
	  echo "Task 1 complete") && \
	(echo "Task 2 starting"; \
	  echo "Task 2 executing..."; \
	  echo "Task 2 complete") && \
	echo "=== Both tasks completed successfully ==="

# Method 70: Combining tasks with make functions
define task1_function
	@echo "Task 1: $(1)"
	@echo "Task 1 executing..."
	@echo "Task 1 complete"
endef

define task2_function
	@echo "Task 2: $(1)"
	@echo "Task 2 executing..."
	@echo "Task 2 complete"
endef

combined-functions:
	@echo "=== Function Combined Tasks ==="
	$(call task1_function,Function Call)
	$(call task2_function,Function Call)
	@echo "=== Function combined execution finished ==="

# Method 71: Combining tasks with conditional execution
combined-conditional:
	@echo "=== Conditional Combined Tasks ==="
	@if [ "$(EXECUTE_TASK1)" = "true" ]; then \
		echo "Task 1 starting"; \
		echo "Task 1 executing..."; \
		echo "Task 1 complete"; \
	fi
	@if [ "$(EXECUTE_TASK2)" = "true" ]; then \
		echo "Task 2 starting"; \
		echo "Task 2 executing..."; \
		echo "Task 2 complete"; \
	fi
	@echo "=== Conditional combined execution finished ==="

# Method 72: Combining tasks with parallel execution
combined-parallel:
	@echo "=== Parallel Combined Tasks ==="
	@(echo "Task 1 starting"; sleep 2; echo "Task 1 complete") &
	@(echo "Task 2 starting"; sleep 3; echo "Task 2 complete") &
	@wait
	@echo "=== Parallel combined execution finished ==="

# Method 73: Combining tasks with file-based coordination
combined-file-coordination:
	@echo "=== File Coordination Combined Tasks ==="
	@echo "Task 1 starting" > /tmp/task1.log
	@echo "Task 1 executing..." >> /tmp/task1.log
	@echo "Task 1 complete" >> /tmp/task1.log
	@echo "Task 2 starting" > /tmp/task2.log
	@echo "Task 2 executing..." >> /tmp/task2.log
	@echo "Task 2 complete" >> /tmp/task2.log
	@echo "Task 1 output: $$(cat /tmp/task1.log)"
	@echo "Task 2 output: $$(cat /tmp/task2.log)"
	@echo "=== File coordination combined execution finished ==="

# Method 74: Combining tasks with make variables
combined-variables:
	@echo "=== Variable Combined Tasks ==="
	$(eval TASK1_RESULT := Task 1 completed)
	$(eval TASK2_RESULT := Task 2 completed)
	@echo "Task 1: $(TASK1_RESULT)"
	@echo "Task 2: $(TASK2_RESULT)"
	@echo "=== Variable combined execution finished ==="

# Method 75: Combining tasks with environment variables
combined-env:
	@echo "=== Environment Combined Tasks ==="
	@export TASK1_STATUS="completed" && \
	export TASK2_STATUS="completed" && \
	echo "Task 1 status: $$TASK1_STATUS" && \
	echo "Task 2 status: $$TASK2_STATUS" && \
	echo "=== Environment combined execution finished ==="

# Method 76: Combining tasks with make's .ONESHELL directive
.ONESHELL:
combined-oneshell:
	@echo "=== OneShell Combined Tasks ==="
	@set -e
	@echo "Task 1 starting"
	@echo "Task 1 executing..."
	@echo "Task 1 complete"
	@echo "Task 2 starting"
	@echo "Task 2 executing..."
	@echo "Task 2 complete"
	@echo "=== OneShell combined execution finished ==="

# Method 77: Combining tasks with make's call function
define combined_call
	@echo "Combined task execution: $(1)"
	@echo "Task 1: $(2)"
	@echo "Task 2: $(3)"
endef

combined-call:
	$(call combined_call,Call Example,Task 1 Data,Task 2 Data)

# Method 78: Combining tasks with make's foreach
combined-foreach:
	@echo "=== Foreach Combined Tasks ==="
	$(foreach task,Task1 Task2,$(eval $(task)_STATUS := completed))
	@echo "Task1_STATUS: $(Task1_STATUS)"
	@echo "Task2_STATUS: $(Task2_STATUS)"
	@echo "=== Foreach combined execution finished ==="

# Method 79: Combining tasks with make's if/else
combined-if-else:
	@echo "=== If/Else Combined Tasks ==="
	@if [ "$(COMBINE_MODE)" = "sequential" ]; then \
		echo "Sequential mode: Task 1 then Task 2"; \
		echo "Task 1 executing..."; \
		echo "Task 2 executing..."; \
	elif [ "$(COMBINE_MODE)" = "parallel" ]; then \
		echo "Parallel mode: Task 1 and Task 2 together"; \
		(echo "Task 1 executing...") & \
		(echo "Task 2 executing...") & \
		wait; \
	else \
		echo "Default mode: Task 1 only"; \
		echo "Task 1 executing..."; \
	fi
	@echo "=== If/Else combined execution finished ==="

# Method 80: Combining tasks with make's eval and call
combined-eval-call:
	@echo "=== Eval/Call Combined Tasks ==="
	$(eval TASK1_CMD := echo "Task 1 executed via eval")
	$(eval TASK2_CMD := echo "Task 2 executed via eval")
	$(TASK1_CMD)
	$(TASK2_CMD)
	@echo "=== Eval/Call combined execution finished ==="

# ========================================
# PARAMETERIZING MAKE TASKS
# ========================================

# Method 81: Parameterized tasks with make variables
PARAM1 ?= default_value1
PARAM2 ?= default_value2

param-task:
	@echo "=== Parameterized Task ==="
	@echo "Parameter 1: $(PARAM1)"
	@echo "Parameter 2: $(PARAM2)"
	@echo "=== Task completed ==="

# Method 82: Parameterized tasks with environment variables
param-env-task:
	@echo "=== Environment Parameterized Task ==="
	@echo "ENV_PARAM1: $(ENV_PARAM1)"
	@echo "ENV_PARAM2: $(ENV_PARAM2)"
	@echo "BUILD_TYPE: $(BUILD_TYPE)"
	@echo "VERSION: $(VERSION)"
	@echo "=== Environment task completed ==="

# Method 83: Parameterized tasks with make's call function
define param_function
	@echo "=== Function Parameterized Task ==="
	@echo "First parameter: $(1)"
	@echo "Second parameter: $(2)"
	@echo "Third parameter: $(3)"
	@echo "=== Function task completed ==="
endef

param-call-task:
	$(call param_function,Value1,Value2,Value3)

# Method 84: Parameterized tasks with pattern rules
param-pattern-%:
	@echo "=== Pattern Parameterized Task ==="
	@echo "Pattern parameter: $*"
	@echo "Target name: $@"
	@echo "=== Pattern task completed ==="

# Method 85: Parameterized tasks with make's eval
param-eval-task:
	@echo "=== Eval Parameterized Task ==="
	$(eval DYNAMIC_PARAM := $(shell echo "Dynamic value: $$(date)"))
	@echo "Dynamic parameter: $(DYNAMIC_PARAM)"
	@echo "User parameter: $(USER_PARAM)"
	@echo "=== Eval task completed ==="

# Method 86: Parameterized tasks with command line arguments
param-cmd-task:
	@echo "=== Command Line Parameterized Task ==="
	@echo "Target: $(TARGET)"
	@echo "Action: $(ACTION)"
	@echo "Mode: $(MODE)"
	@echo "=== Command line task completed ==="

# Method 87: Parameterized tasks with make's foreach
param-foreach-task:
	@echo "=== Foreach Parameterized Task ==="
	$(foreach param,param1 param2 param3 param4,$(eval $(param)_VALUE := $(shell echo "Value for $(param)")))
	@echo "param1_VALUE: $(param1_VALUE)"
	@echo "param2_VALUE: $(param2_VALUE)"
	@echo "param3_VALUE: $(param3_VALUE)"
	@echo "param4_VALUE: $(param4_VALUE)"
	@echo "=== Foreach task completed ==="

# Method 88: Parameterized tasks with make's if/else
param-conditional-task:
	@echo "=== Conditional Parameterized Task ==="
	@if [ "$(TASK_MODE)" = "debug" ]; then \
		echo "Debug mode enabled"; \
		echo "Debug parameter: $(DEBUG_PARAM)"; \
	elif [ "$(TASK_MODE)" = "release" ]; then \
		echo "Release mode enabled"; \
		echo "Release parameter: $(RELEASE_PARAM)"; \
	else \
		echo "Default mode"; \
		echo "Default parameter: $(DEFAULT_PARAM)"; \
	fi
	@echo "=== Conditional task completed ==="

# Method 89: Parameterized tasks with make's shell function
param-shell-task:
	@echo "=== Shell Parameterized Task ==="
	@echo "Current user: $(shell whoami)"
	@echo "Current directory: $(shell pwd)"
	@echo "System info: $(shell uname -a)"
	@echo "Custom shell param: $(shell echo "Custom: $(CUSTOM_SHELL_PARAM)")"
	@echo "=== Shell task completed ==="

# Method 90: Parameterized tasks with make's override directive
param-override-task:
	@echo "=== Override Parameterized Task ==="
	$(eval override OVERRIDE_PARAM := $(OVERRIDE_VALUE))
	@echo "Override parameter: $(OVERRIDE_PARAM)"
	@echo "Original value: $(OVERRIDE_VALUE)"
	@echo "=== Override task completed ==="

# Method 91: Parameterized tasks with make's .SECONDEXPANSION
.SECONDEXPANSION:
param-second-expansion: $$(addprefix param-target-,$$(PARAM_LIST))
	@echo "=== Second Expansion Parameterized Task ==="
	@echo "Parameter list: $(PARAM_LIST)"
	@echo "=== Second expansion task completed ==="

param-target-%:
	@echo "Processing parameter: $*"

# Method 92: Parameterized tasks with make's define and call
define param_template
	@echo "=== Template Parameterized Task ==="
	@echo "Template name: $(1)"
	@echo "Template data: $(2)"
	@echo "Template config: $(3)"
	@echo "=== Template task completed ==="
endef

param-template-task:
	$(call param_template,MyTemplate,MyData,MyConfig)

# Method 93: Parameterized tasks with make's include directive
param-include-task:
	@echo "=== Include Parameterized Task ==="
	@echo "Included parameter: $(INCLUDED_PARAM)"
	@echo "Config file: $(CONFIG_FILE)"
	@echo "=== Include task completed ==="

# Method 94: Parameterized tasks with make's export directive
param-export-task:
	@echo "=== Export Parameterized Task ==="
	@export EXPORTED_PARAM="Exported value"
	@export ANOTHER_PARAM="Another value"
	@echo "Exported parameter: $$EXPORTED_PARAM"
	@echo "Another parameter: $$ANOTHER_PARAM"
	@echo "=== Export task completed ==="

# Method 95: Parameterized tasks with make's .ONESHELL directive
.ONESHELL:
param-oneshell-task:
	@echo "=== OneShell Parameterized Task ==="
	@set -e
	@export ONESHELL_PARAM="OneShell value"
	@echo "OneShell parameter: $$ONESHELL_PARAM"
	@echo "User parameter: $(USER_PARAM)"
	@echo "=== OneShell task completed ==="

# Method 96: Parameterized tasks with make's .PHONY directive
.PHONY: param-phony-%

param-phony-%:
	@echo "=== Phony Parameterized Task ==="
	@echo "Phony parameter: $*"
	@echo "Target: $@"
	@echo "=== Phony task completed ==="

# Method 97: Parameterized tasks with make's .INTERMEDIATE directive
param-intermediate-%:
	@echo "=== Intermediate Parameterized Task ==="
	@echo "Creating intermediate file for parameter: $*"
	@echo "Parameter: $*" > $@
	@echo "=== Intermediate task completed ==="

param-intermediate-all: param-intermediate-file1 param-intermediate-file2 param-intermediate-file3
	@echo "All intermediate files created"

# Method 98: Parameterized tasks with make's .PRECIOUS directive
param-precious-%:
	@echo "=== Precious Parameterized Task ==="
	@echo "Creating precious file for parameter: $*"
	@echo "Precious parameter: $*" > $@
	@echo "=== Precious task completed ==="

param-precious-all: param-precious-data1 param-precious-data2 param-precious-data3
	@echo "All precious files created"

.PRECIOUS: param-precious-data1 param-precious-data2 param-precious-data3

# Method 99: Parameterized tasks with make's .SUFFIXES directive
.SUFFIXES: .param

%.param:
	@echo "=== Suffix Parameterized Task ==="
	@echo "Processing file: $<"
	@echo "Target: $@"
	@echo "Stem: $*"
	@echo "=== Suffix task completed ==="

param-suffix-task: test.param

# Method 100: Parameterized tasks with make's .DEFAULT_GOAL directive
param-default-task:
	@echo "=== Default Parameterized Task ==="
	@echo "Default parameter: $(DEFAULT_PARAM)"
	@echo "Fallback parameter: $(FALLBACK_PARAM)"
	@echo "=== Default task completed ==="

# ========================================
# THE @ SIGN IN MAKE - COMMAND ECHOING
# ========================================

# Method 101: Demonstrating @ sign behavior
echo-demo:
	echo "This command will be echoed (shown)"
	@echo "This command will NOT be echoed (hidden)"
	echo "This command will be echoed again"

# Method 102: Comparing with and without @
verbose-task:
	echo "Step 1: Creating directory"
	mkdir -p build
	echo "Step 2: Creating file"
	echo "content" > build/test.txt
	echo "Step 3: Listing files"
	ls -la build/

quiet-task:
	@echo "Step 1: Creating directory"
	@mkdir -p build
	@echo "Step 2: Creating file"
	@echo "content" > build/test.txt
	@echo "Step 3: Listing files"
	@ls -la build/

# Method 103: Mixed @ and non-@ commands
mixed-task:
	@echo "=== Starting mixed task ==="
	echo "This command is visible"
	@echo "This command is hidden"
	echo "Another visible command"
	@echo "=== Mixed task completed ==="

# Method 104: @ with shell commands
shell-demo:
	@echo "Shell commands with @"
	@for i in 1 2 3; do \
		echo "Iteration $$i"; \
	done
	@echo "Shell demo completed"

# Method 105: @ with conditional commands
conditional-demo:
	@echo "Conditional commands with @"
	@if [ "$(DEBUG)" = "true" ]; then \
		echo "Debug mode enabled"; \
	else \
		echo "Debug mode disabled"; \
	fi
	@echo "Conditional demo completed"

# Method 106: @ with make functions
function-demo:
	@echo "Function calls with @"
	$(call param_function,Value1,Value2)
	@echo "Function demo completed"

# Method 107: @ with error handling
error-demo:
	@echo "Error handling with @"
	@set -e
	@echo "Command 1"
	@echo "Command 2"
	@echo "Command 3"
	@echo "Error demo completed"

# Method 108: @ with file operations
file-demo:
	@echo "File operations with @"
	@mkdir -p temp
	@echo "File content" > temp/test.txt
	@cat temp/test.txt
	@rm -rf temp
	@echo "File demo completed"

# Method 109: @ with environment variables
env-demo:
	@echo "Environment variables with @"
	@echo "USER: $(USER)"
	@echo "PWD: $(PWD)"
	@echo "HOME: $(HOME)"
	@echo "Env demo completed"

# Method 110: @ with parallel execution
parallel-demo:
	@echo "Parallel execution with @"
	@(echo "Job 1 starting"; sleep 2; echo "Job 1 complete") &
	@(echo "Job 2 starting"; sleep 1; echo "Job 2 complete") &
	@wait
	@echo "Parallel demo completed"

# Method 111: Demonstrating .SILENT directive
.SILENT: silent-task

silent-task:
	echo "This command is silent due to .SILENT"
	echo "This command is also silent"
	echo "All commands in this target are silent"

# Method 112: Comparing .SILENT with @
silent-vs-at:
	@echo "This command uses @"
	echo "This command is echoed"
	@echo "This command also uses @"

# Method 113: @ with make variables
variable-demo:
	@echo "Variable usage with @"
	@echo "PARAM1: $(PARAM1)"
	@echo "PARAM2: $(PARAM2)"
	@echo "Variable demo completed"

# Method 114: @ with command substitution
substitution-demo:
	@echo "Command substitution with @"
	@echo "Date: $(shell date)"
	@echo "User: $(shell whoami)"
	@echo "PWD: $(shell pwd)"
	@echo "Substitution demo completed"

# Method 115: @ with loops
loop-demo:
	@echo "Loop with @"
	@for i in 1 2 3 4 5; do \
		echo "Loop iteration $$i"; \
	done
	@echo "Loop demo completed"

# Method 116: @ with debugging
debug-demo:
	@echo "Debugging with @"
	@echo "Debug: Starting task"
	@echo "Debug: Creating file"
	@echo "test content" > debug.txt
	@echo "Debug: File created"
	@cat debug.txt
	@echo "Debug: File contents shown"
	@rm debug.txt
	@echo "Debug: File removed"
	@echo "Debug demo completed"

# Method 117: @ with make's call function
call-demo:
	@echo "Call function with @"
	$(call param_function,CallParam1,CallParam2)
	@echo "Call demo completed"

# Method 118: @ with make's eval function
eval-demo:
	@echo "Eval function with @"
	$(eval TEST_VAR := "Eval test value")
	@echo "TEST_VAR: $(TEST_VAR)"
	@echo "Eval demo completed"

# Method 119: @ with make's foreach function
foreach-demo:
	@echo "Foreach function with @"
	$(foreach item,item1 item2 item3,$(eval $(item)_VALUE := "Value for $(item)"))
	@echo "item1_VALUE: $(item1_VALUE)"
	@echo "item2_VALUE: $(item2_VALUE)"
	@echo "item3_VALUE: $(item3_VALUE)"
	@echo "Foreach demo completed"

# Method 120: @ with make's if function
if-demo:
	@echo "If function with @"
	@if [ "$(TEST_MODE)" = "true" ]; then \
		echo "Test mode is enabled"; \
	else \
		echo "Test mode is disabled"; \
	fi
	@echo "If demo completed"

# ========================================
# MULTI-LINE FOREACH STATEMENTS IN MAKE
# ========================================

# Method 121: Basic multi-line foreach with backslashes
foreach-multiline-basic:
	@echo "=== Basic Multi-line Foreach ==="
	$(foreach item, \
		item1 \
		item2 \
		item3 \
		item4 \
		item5, \
		$(eval $(item)_STATUS := "Processed") \
	)
	@echo "item1_STATUS: $(item1_STATUS)"
	@echo "item2_STATUS: $(item2_STATUS)"
	@echo "item3_STATUS: $(item3_STATUS)"
	@echo "item4_STATUS: $(item4_STATUS)"
	@echo "item5_STATUS: $(item5_STATUS)"

# Method 122: Multi-line foreach with variables
LARGE_ARRAY := item1 item2 item3 item4 item5 item6 item7 item8 item9 item10

foreach-multiline-vars:
	@echo "=== Multi-line Foreach with Variables ==="
	$(foreach item, \
		$(LARGE_ARRAY), \
		$(eval $(item)_PROCESSED := "Yes") \
		$(eval $(item)_TIMESTAMP := $(shell date +%s)) \
	)
	@echo "Processing complete for $(words $(LARGE_ARRAY)) items"

# Method 123: Multi-line foreach with complex operations
foreach-multiline-complex:
	@echo "=== Complex Multi-line Foreach ==="
	$(foreach item, \
		alpha \
		beta \
		gamma \
		delta \
		epsilon, \
		$(eval $(item)_UPPER := $(shell echo $(item) | tr '[:lower:]' '[:upper:]')) \
		$(eval $(item)_LENGTH := $(shell echo $(item) | wc -c)) \
		$(eval $(item)_REVERSE := $(shell echo $(item) | rev)) \
	)
	@echo "alpha_UPPER: $(alpha_UPPER), LENGTH: $(alpha_LENGTH), REVERSE: $(alpha_REVERSE)"
	@echo "beta_UPPER: $(beta_UPPER), LENGTH: $(beta_LENGTH), REVERSE: $(beta_REVERSE)"

# Method 124: Multi-line foreach with conditional logic
foreach-multiline-conditional:
	@echo "=== Conditional Multi-line Foreach ==="
	$(foreach item, \
		debug \
		info \
		warning \
		error \
		critical, \
		$(if $(filter debug info,$(item)), \
			$(eval $(item)_LEVEL := "Low"), \
			$(eval $(item)_LEVEL := "High") \
		) \
		$(eval $(item)_COLOR := $(if $(filter debug,$(item)),green,$(if $(filter error critical,$(item)),red,yellow))) \
	)
	@echo "debug_LEVEL: $(debug_LEVEL), COLOR: $(debug_COLOR)"
	@echo "error_LEVEL: $(error_LEVEL), COLOR: $(error_COLOR)"

# Method 125: Multi-line foreach with function calls
define process_item
	@echo "Processing $(1)..."
	@echo "Status: $(2)"
	@echo "Timestamp: $(shell date)"
endef

foreach-multiline-functions:
	@echo "=== Multi-line Foreach with Functions ==="
	$(foreach item, \
		file1 \
		file2 \
		file3 \
		file4, \
		$(call process_item,$(item),Processing) \
	)

# Method 126: Multi-line foreach with shell commands
foreach-multiline-shell:
	@echo "=== Multi-line Foreach with Shell Commands ==="
	$(foreach dir, \
		src \
		include \
		lib \
		bin \
		test, \
		$(eval $(dir)_EXISTS := $(shell test -d $(dir) && echo "Yes" || echo "No")) \
		$(eval $(dir)_FILES := $(shell find $(dir) -type f 2>/dev/null | wc -l)) \
	)
	@echo "src_EXISTS: $(src_EXISTS), FILES: $(src_FILES)"
	@echo "include_EXISTS: $(include_EXISTS), FILES: $(include_FILES)"

# Method 127: Multi-line foreach with file operations
foreach-multiline-files:
	@echo "=== Multi-line Foreach with File Operations ==="
	$(foreach file, \
		config.txt \
		data.json \
		output.log \
		error.log \
		debug.log, \
		$(eval $(file)_SIZE := $(shell test -f $(file) && stat -f%z $(file) 2>/dev/null || echo "0")) \
		$(eval $(file)_MODIFIED := $(shell test -f $(file) && stat -f%m $(file) 2>/dev/null || echo "0")) \
	)

# Method 128: Multi-line foreach with make variables
foreach-multiline-makevars:
	@echo "=== Multi-line Foreach with Make Variables ==="
	$(foreach var, \
		BUILD_TYPE \
		VERSION \
		TARGET \
		DEBUG \
		OPTIMIZE, \
		$(eval $(var)_VALUE := $($(var))) \
		$(eval $(var)_SET := $(if $($(var)),Yes,No)) \
	)
	@echo "BUILD_TYPE_VALUE: $(BUILD_TYPE_VALUE), SET: $(BUILD_TYPE_SET)"
	@echo "VERSION_VALUE: $(VERSION_VALUE), SET: $(VERSION_SET)"

# Method 129: Multi-line foreach with environment variables
foreach-multiline-env:
	@echo "=== Multi-line Foreach with Environment Variables ==="
	$(foreach envvar, \
		HOME \
		USER \
		PATH \
		SHELL \
		PWD, \
		$(eval $(envvar)_ENV := $(shell echo $$$(envvar))) \
	)
	@echo "HOME_ENV: $(HOME_ENV)"
	@echo "USER_ENV: $(USER_ENV)"

# Method 130: Multi-line foreach with nested operations
foreach-multiline-nested:
	@echo "=== Nested Multi-line Foreach ==="
	$(foreach category, \
		development \
		testing \
		production, \
		$(foreach subitem, \
			build \
			deploy \
			monitor, \
			$(eval $(category)_$(subitem)_STATUS := "Pending") \
			$(eval $(category)_$(subitem)_PRIORITY := $(if $(filter development,$(category)),Low,$(if $(filter production,$(category)),High,Medium))) \
		) \
	)
	@echo "development_build_STATUS: $(development_build_STATUS), PRIORITY: $(development_build_PRIORITY)"
	@echo "production_deploy_STATUS: $(production_deploy_STATUS), PRIORITY: $(production_deploy_PRIORITY)"

# Method 131: Multi-line foreach with error handling
foreach-multiline-error:
	@echo "=== Multi-line Foreach with Error Handling ==="
	$(foreach command, \
		ls \
		cat \
		nonexistent \
		whoami, \
		$(eval $(command)_RESULT := $(shell $(command) 2>&1 || echo "Command failed")) \
		$(eval $(command)_SUCCESS := $(if $(filter Command failed,$($(command)_RESULT)),No,Yes)) \
	)
	@echo "ls_SUCCESS: $(ls_SUCCESS)"
	@echo "nonexistent_SUCCESS: $(nonexistent_SUCCESS)"

# Method 132: Multi-line foreach with dynamic content
foreach-multiline-dynamic:
	@echo "=== Dynamic Multi-line Foreach ==="
	$(foreach number, \
		$(shell seq 1 5), \
		$(eval ITEM_$(number) := "Dynamic item $(number)") \
		$(eval ITEM_$(number)_SQUARE := $(shell echo $(number) \* $(number) | bc)) \
		$(eval ITEM_$(number)_CUBE := $(shell echo $(number) \* $(number) \* $(number) | bc)) \
	)
	@echo "ITEM_3: $(ITEM_3), SQUARE: $(ITEM_3_SQUARE), CUBE: $(ITEM_3_CUBE)"

# Method 133: Multi-line foreach with conditional execution
foreach-multiline-conditional-exec:
	@echo "=== Conditional Execution Multi-line Foreach ==="
	$(foreach task, \
		compile \
		test \
		package \
		deploy, \
		$(if $(filter $(EXECUTE_TASKS),$(task)), \
			$(eval $(task)_EXECUTE := "Yes") \
			$(eval $(task)_COMMAND := "Will execute $(task)"), \
			$(eval $(task)_EXECUTE := "No") \
			$(eval $(task)_COMMAND := "Skipping $(task)") \
		) \
	)
	@echo "compile_EXECUTE: $(compile_EXECUTE), COMMAND: $(compile_COMMAND)"
	@echo "deploy_EXECUTE: $(deploy_EXECUTE), COMMAND: $(deploy_COMMAND)"

# Method 134: Multi-line foreach with template generation
define generate_template
	@echo "Generating template for $(1)..."
	@echo "Template: $(2)" > templates/$(1).tmpl
	@echo "Template $(1) generated successfully"
endef

foreach-multiline-templates:
	@echo "=== Template Generation Multi-line Foreach ==="
	@mkdir -p templates
	$(foreach template, \
		config \
		service \
		deployment \
		ingress, \
		$(call generate_template,$(template),Template content for $(template)) \
	)

# Method 135: Multi-line foreach with parallel processing simulation
foreach-multiline-parallel:
	@echo "=== Parallel Processing Multi-line Foreach ==="
	$(foreach job, \
		job1 \
		job2 \
		job3 \
		job4, \
		$(eval $(job)_PID := $(shell echo $$RANDOM)) \
		$(eval $(job)_START := $(shell date +%s)) \
		$(eval $(job)_STATUS := "Running") \
	)
	@echo "All jobs started in parallel simulation"

# ========================================
# VARIABLE SYNTAX IN MAKE: $() vs ${}
# ========================================

# Method 136: Demonstrating $() vs ${} for Make variables
MAKE_VAR := "This is a Make variable"

var-syntax-demo:
	@echo "=== Variable Syntax Demo ==="
	@echo "Make variable with \$(): $(MAKE_VAR)"
	@echo "Make variable with \${}: ${MAKE_VAR}"
	@echo "Both work the same way!"

# Method 137: Demonstrating $() vs ${} for environment variables
var-env-demo:
	@echo "=== Environment Variable Syntax Demo ==="
	@echo "Environment variable with \$(): $(USER)"
	@echo "Environment variable with \${}: ${USER}"
	@echo "Environment variable with \$(): $(HOME)"
	@echo "Environment variable with \${}: ${HOME}"
	@echo "Both work the same way!"

# Method 138: Mixed variable types with both syntaxes
MIXED_VAR := "Mixed variable"

var-mixed-demo:
	@echo "=== Mixed Variable Types Demo ==="
	@echo "Make variable: $(MIXED_VAR)"
	@echo "Make variable: ${MIXED_VAR}"
	@echo "Environment variable: $(PWD)"
	@echo "Environment variable: ${PWD}"
	@echo "Shell command result: $(shell whoami)"
	@echo "Shell command result: ${shell whoami}"

# Method 139: Complex variable expansion with both syntaxes
COMPLEX_VAR := "complex"
SIMPLE_VAR := "simple"

var-complex-demo:
	@echo "=== Complex Variable Expansion Demo ==="
	@echo "Complex with \$(): $(COMPLEX_VAR)_value"
	@echo "Complex with \${}: ${COMPLEX_VAR}_value"
	@echo "Nested with \$(): $(SIMPLE_VAR)_$(COMPLEX_VAR)"
	@echo "Nested with \${}: ${SIMPLE_VAR}_${COMPLEX_VAR}"

# Method 140: Variable expansion in functions with both syntaxes
define var_function
	@echo "Function parameter 1: $(1)"
	@echo "Function parameter 2: $(2)"
	@echo "Make variable in function: $(MAKE_VAR)"
	@echo "Make variable in function: ${MAKE_VAR}"
	@echo "Environment variable in function: $(USER)"
	@echo "Environment variable in function: ${USER}"
endef

var-function-demo:
	@echo "=== Variable Expansion in Functions Demo ==="
	$(call var_function,Param1,Param2)

# Method 141: Variable expansion in shell commands with both syntaxes
var-shell-demo:
	@echo "=== Variable Expansion in Shell Commands Demo ==="
	@echo "Shell command with \$(): $(shell echo "User: $(USER)")"
	@echo "Shell command with \${}: $(shell echo "User: ${USER}")"
	@echo "Shell command with \$(): $(shell echo "Home: $(HOME)")"
	@echo "Shell command with \${}: $(shell echo "Home: ${HOME}")"

# Method 142: Variable expansion in conditional statements with both syntaxes
var-conditional-demo:
	@echo "=== Variable Expansion in Conditionals Demo ==="
	@if [ "$(USER)" = "$(shell whoami)" ]; then \
		echo "User matches with \$()"; \
	fi
	@if [ "${USER}" = "$(shell whoami)" ]; then \
		echo "User matches with \${}"; \
	fi
	@if [ "$(MAKE_VAR)" = "This is a Make variable" ]; then \
		echo "Make variable matches with \$()"; \
	fi
	@if [ "${MAKE_VAR}" = "This is a Make variable" ]; then \
		echo "Make variable matches with \${}"; \
	fi

# Method 143: Variable expansion in foreach loops with both syntaxes
var-foreach-demo:
	@echo "=== Variable Expansion in Foreach Demo ==="
	$(foreach item, \
		item1 \
		item2, \
		$(eval $(item)_VAR := "Value for $(item)") \
		$(eval $(item)_VAR2 := "Value for ${item}") \
	)
	@echo "item1_VAR with \$(): $(item1_VAR)"
	@echo "item1_VAR2 with \${}: $(item1_VAR2)"

# Method 144: Variable expansion in eval statements with both syntaxes
var-eval-demo:
	@echo "=== Variable Expansion in Eval Demo ==="
	$(eval EVAL_VAR1 := "Eval variable 1")
	$(eval EVAL_VAR2 := "Eval variable 2")
	@echo "Eval variable with \$(): $(EVAL_VAR1)"
	@echo "Eval variable with \${}: ${EVAL_VAR2}"

# Method 145: Variable expansion in call functions with both syntaxes
define call_function
	@echo "Call function with \$(): $(1)"
	@echo "Call function with \${}: ${1}"
	@echo "Make variable in call: $(MAKE_VAR)"
	@echo "Make variable in call: ${MAKE_VAR}"
endef

var-call-demo:
	@echo "=== Variable Expansion in Call Demo ==="
	$(call call_function,TestParameter)

# Method 146: Variable expansion in shell command substitution with both syntaxes
var-substitution-demo:
	@echo "=== Variable Expansion in Substitution Demo ==="
	@echo "Substitution with \$(): $(shell echo "Current user: $(USER)")"
	@echo "Substitution with \${}: $(shell echo "Current user: ${USER}")"
	@echo "Substitution with \$(): $(shell echo "Current home: $(HOME)")"
	@echo "Substitution with \${}: $(shell echo "Current home: ${HOME}")"

# Method 147: Variable expansion in file operations with both syntaxes
var-file-demo:
	@echo "=== Variable Expansion in File Operations Demo ==="
	@echo "File content with \$(): $(shell cat /etc/hostname 2>/dev/null || echo "File not found")"
	@echo "File content with \${}: ${shell cat /etc/hostname 2>/dev/null || echo "File not found"}"
	@echo "Directory listing with \$(): $(shell ls -la $(HOME) | head -3)"
	@echo "Directory listing with \${}: $(shell ls -la ${HOME} | head -3)"

# Method 148: Variable expansion in parallel execution with both syntaxes
var-parallel-demo:
	@echo "=== Variable Expansion in Parallel Demo ==="
	@(echo "Parallel job 1 with \$(): $(USER)") &
	@(echo "Parallel job 2 with \${}: ${USER}") &
	@wait
	@echo "Parallel execution completed"

# Method 149: Variable expansion in template generation with both syntaxes
define template_function
	@echo "Template for $(1) with \$(): $(USER)"
	@echo "Template for ${1} with \${}: ${USER}"
	@echo "Template content: $(2)"
endef

var-template-demo:
	@echo "=== Variable Expansion in Templates Demo ==="
	$(call template_function,TestTemplate,Template content here)

# Method 150: Variable expansion in error handling with both syntaxes
var-error-demo:
	@echo "=== Variable Expansion in Error Handling Demo ==="
	@if [ -z "$(USER)" ]; then \
		echo "Error: USER variable is empty with \$()"; \
	else \
		echo "USER variable is set with \$(): $(USER)"; \
	fi
	@if [ -z "${USER}" ]; then \
		echo "Error: USER variable is empty with \${}"; \
	else \
		echo "USER variable is set with \${}: ${USER}"; \
	fi

# Help target to show all available targets
help:
	@echo "Available targets:"
	@echo "  target1-20    - Different chaining methods"
	@echo "  stage1-3      - Global make variables (recommended)"
	@echo "  stage6-7      - File-based variable passing"
	@echo "  stage12-13    - Eval/call function variables"
	@echo "  stage16-17    - Command substitution variables"
	@echo "  stage21-22    - Call function with parameters"
	@echo "  stage25-26    - Shell function variables"
	@echo "  stage29-30    - Conditional variables"
	@echo "  setup         - Setup environment"
	@echo "  build         - Build project (depends on setup)"
	@echo "  test          - Run tests (depends on build)"
	@echo "  deploy        - Deploy (depends on test)"
	@echo "  clean         - Clean up files"
	@echo "  parallel-all  - Run parallel tasks"
	@echo "  help          - Show this help message"
	@echo ""
	@echo "Variable passing examples:"
	@echo "  make stage3          # Global variables"
	@echo "  make stage7          # File-based passing"
	@echo "  make stage13         # Eval/call functions"
	@echo "  make stage30 debug   # Conditional variables"
	@echo ""
	@echo "Environment variable examples:"
	@echo "  make env-test        # Basic environment access"
	@echo "  make env-custom      # Custom environment variables"
	@echo "  make env-conditional # Conditional logic"
	@echo "  make env-file-ops    # Environment in file operations"
	@echo ""
	@echo "Test with environment variables:"
	@echo "  DEBUG=true make env-conditional"
	@echo "  BUILD_TYPE=debug make env-conditional-compile"
	@echo "  CUSTOM_VAR=test make env-custom"
	@echo ""
	@echo "Parallel execution examples:"
	@echo "  make parallel-all        # Basic parallel execution"
	@echo "  make parallel-shell      # Shell-based parallel"
	@echo "  make parallel-jobs       # Job simulation"
	@echo "  make parallel-groups     # Group-based parallel"
	@echo "  make sequential-all      # Sequential execution"
	@echo "  make parallel-phony      # Phony targets parallel"
	@echo ""
	@echo "Parallel execution with make flags:"
	@echo "  make -j4 parallel-all    # Limit to 4 jobs"
	@echo "  make -j parallel-all     # Unlimited jobs"
	@echo "  make -j1 parallel-all    # Sequential (1 job)"
	@echo ""
	@echo "Task combination examples:"
	@echo "  make combined-tasks      # Dependencies method"
	@echo "  make combined-single     # Single target method"
	@echo "  make combined-shell      # Shell chaining method"
	@echo "  make combined-functions  # Function method"
	@echo "  make combined-parallel   # Parallel combination"
	@echo "  make combined-oneshell   # OneShell method"
	@echo ""
	@echo "Conditional task combination:"
	@echo "  EXECUTE_TASK1=true make combined-conditional"
	@echo "  COMBINE_MODE=parallel make combined-if-else"
	@echo ""
	@echo "Task parameterization examples:"
	@echo "  make param-task                    # Basic parameters"
	@echo "  make param-call-task              # Function parameters"
	@echo "  make param-pattern-test           # Pattern parameters"
	@echo "  make param-conditional-task       # Conditional parameters"
	@echo "  make param-phony-custom           # Phony parameters"
	@echo ""
	@echo "Parameterized task usage:"
	@echo "  PARAM1=value1 make param-task"
	@echo "  TASK_MODE=debug make param-conditional-task"
	@echo "  TARGET=app ACTION=build make param-cmd-task"
	@echo ""
	@echo "@ sign examples (command echoing):"
	@echo "  make echo-demo          # Compare with/without @"
	@echo "  make verbose-task       # All commands echoed"
	@echo "  make quiet-task         # All commands hidden"
	@echo "  make mixed-task         # Mixed @ and non-@"
	@echo "  make silent-task        # .SILENT directive"
	@echo ""
	@echo "Multi-line foreach examples:"
	@echo "  make foreach-multiline-basic      # Basic multi-line foreach"
	@echo "  make foreach-multiline-vars       # With variables"
	@echo "  make foreach-multiline-complex    # Complex operations"
	@echo "  make foreach-multiline-nested     # Nested foreach"
	@echo "  make foreach-multiline-templates  # Template generation"
	@echo ""
	@echo "Variable syntax examples ($() vs ${}):"
	@echo "  make var-syntax-demo              # Basic syntax comparison"
	@echo "  make var-env-demo                 # Environment variables"
	@echo "  make var-mixed-demo               # Mixed variable types"
	@echo "  make var-complex-demo             # Complex expansion"
	@echo "  make var-function-demo            # In functions" 