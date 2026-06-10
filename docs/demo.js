const materials = [
  { name: "Aluminum CRV by Weight", unit: "weight", quantityLabel: "lb", rate: 1.72 },
  { name: "Plastic CRV by Weight", unit: "weight", quantityLabel: "lb", rate: 0.80 },
  { name: "Glass CRV by Weight", unit: "weight", quantityLabel: "lb", rate: 0.10 },
  { name: "Aluminum CRV by Count", unit: "count", quantityLabel: "each", rate: 0.05 },
  { name: "Scrap Aluminum by Weight", unit: "weight", quantityLabel: "lb", rate: 1.15 },
  { name: "Manual Adjustment", unit: "manual", quantityLabel: "item", rate: 3.0 },
];

const lineItems = [
  { material: materials[0], quantity: 18.5 },
  { material: materials[3], quantity: 42 },
];

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

function activateTab(targetId) {
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.target === targetId);
  });
  document.querySelectorAll(".screen").forEach((screen) => {
    screen.classList.toggle("active", screen.id === targetId);
  });
}

function selectedMaterial() {
  const select = document.querySelector("#material-select");
  return materials[Number(select.value)] || materials[0];
}

function refreshMaterialFields() {
  const material = selectedMaterial();
  document.querySelector("#unit-type").value = material.unit;
  document.querySelector("#rate").value = `${money.format(material.rate)} per ${material.quantityLabel}`;
}

function renderLineItems() {
  const body = document.querySelector("#line-items");
  const total = lineItems.reduce(
    (sum, item) => sum + item.quantity * item.material.rate,
    0,
  );
  body.innerHTML = lineItems
    .map((item) => {
      const subtotal = item.quantity * item.material.rate;
      return `<tr>
        <td>${item.material.name}</td>
        <td>${item.material.unit}</td>
        <td>${item.quantity}</td>
        <td>${money.format(item.material.rate)}</td>
        <td>${money.format(subtotal)}</td>
      </tr>`;
    })
    .join("");
  document.querySelector("#transaction-total").textContent = money.format(total);
}

function addDemoLine() {
  const material = selectedMaterial();
  const quantity = Number(document.querySelector("#quantity").value || "0");
  if (quantity <= 0) {
    return;
  }
  lineItems.push({ material, quantity });
  renderLineItems();
}

function showStaticSaveNotice() {
  const button = document.querySelector("#save-transaction");
  button.textContent = "Static demo only";
  window.setTimeout(() => {
    button.textContent = "Save Transaction";
  }, 1400);
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.target));
  });

  const materialSelect = document.querySelector("#material-select");
  materialSelect.innerHTML = materials
    .map((material, index) => `<option value="${index}">${material.name}</option>`)
    .join("");
  materialSelect.addEventListener("change", refreshMaterialFields);

  document.querySelector("#add-line").addEventListener("click", addDemoLine);
  document.querySelector("#save-transaction").addEventListener("click", showStaticSaveNotice);

  document.querySelector("#operator-select").addEventListener("change", (event) => {
    const status = event.target.value.includes("Operator") ? "PIN not set" : "Verified";
    document.querySelector("#verification-status").value = status;
  });

  refreshMaterialFields();
  renderLineItems();
});
