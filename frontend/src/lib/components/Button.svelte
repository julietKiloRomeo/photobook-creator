<script lang="ts">
  export let label: string;
  export let variant: "primary" | "ghost" | "danger" = "primary";
  export let type: "button" | "submit" = "button";
  export let disabled = false;
</script>

<button {type} class="btn {variant}" {disabled} on:click>
  {label}
</button>

<style>
  .btn {
    appearance: none;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    padding: 10px 16px;
    font-weight: 500;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
  }
  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .primary {
    background: var(--color-accent);
    color: #fff;
  }
  .primary:not(:disabled):hover {
    background: #3a35a3;
  }
  .ghost {
    background: transparent;
    color: var(--color-text);
    border-color: var(--color-border);
  }
  .ghost:not(:disabled):hover {
    background: var(--color-border-soft);
  }
  .danger {
    background: transparent;
    color: var(--color-danger);
    border-color: var(--color-border);
  }
  .danger:not(:disabled):hover {
    background: #fbeae6;
  }
</style>
