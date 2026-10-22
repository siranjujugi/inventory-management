<template>
  <div class="restocking">
    <div class="page-header">
      <h2>Restocking recommendations</h2>
      <p>Use the demand forecast to prioritize replenishment within your available budget.</p>
    </div>

    <div v-if="loading" class="loading">Loading demand and inventory data...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <section class="card budget-card">
        <div class="budget-heading">
          <div>
            <h3 class="card-title">Available budget</h3>
            <p>Recommendations update as you adjust the budget.</p>
          </div>
          <output for="restocking-budget" class="budget-value">{{ formatCurrency(budget) }}</output>
        </div>
        <label class="visually-hidden" for="restocking-budget">Available budget in US dollars</label>
        <input
          id="restocking-budget"
          v-model.number="budget"
          class="budget-slider"
          type="range"
          min="0"
          max="10000"
          step="100"
        />
        <div class="slider-labels">
          <span>$0</span>
          <span>$10,000</span>
        </div>
      </section>

      <section class="recommendations card">
        <div class="section-heading">
          <div>
            <h3 class="card-title">Recommended items</h3>
            <p>Highest forecasted demand first. Quantities are limited to forecast demand minus current stock and the available budget.</p>
          </div>
          <div class="budget-summary">
            <span>{{ recommendedItems.length }} item{{ recommendedItems.length === 1 ? '' : 's' }}</span>
            <strong>{{ formatCurrency(recommendedTotal) }} of {{ formatCurrency(budget) }}</strong>
          </div>
        </div>

        <div v-if="matchedForecasts.length === 0" class="empty-state">
          No demand forecasts have matching inventory and cost data.
        </div>
        <div v-else class="table-container">
          <table class="restocking-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>SKU</th>
                <th>Forecast</th>
                <th>On hand</th>
                <th>Forecast gap</th>
                <th>Unit cost</th>
                <th>Recommended qty</th>
                <th>Order cost</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in budgetedRecommendations" :key="item.forecast.item_sku">
                <td>
                  <strong>{{ item.inventory.name }}</strong>
                  <span class="item-subtitle">{{ item.forecast.trend }} demand</span>
                </td>
                <td>{{ item.inventory.sku }}</td>
                <td>{{ item.forecast.forecasted_demand }}</td>
                <td>{{ item.inventory.quantity_on_hand }}</td>
                <td>{{ item.forecastGap }}</td>
                <td>{{ formatCurrency(item.inventory.unit_cost) }}</td>
                <td>
                  <span :class="{ muted: item.recommendedQuantity === 0 }">
                    {{ item.recommendedQuantity }}
                  </span>
                </td>
                <td>{{ formatCurrency(item.recommendedQuantity * item.inventory.unit_cost) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <p v-if="unmatchedForecasts.length" class="data-note">
          {{ unmatchedForecasts.length }} forecast item{{ unmatchedForecasts.length === 1 ? '' : 's' }} omitted because no inventory record is available to determine current stock and unit cost.
        </p>
        <p v-if="budget === 0" class="data-note">Set a budget above $0 to see affordable quantities.</p>

        <div class="order-actions">
          <p v-if="submitError" class="submit-error" role="alert">{{ submitError }}</p>
          <p v-if="submittedOrder" class="submit-success" role="status">
            Order submitted for {{ formatCurrency(submittedOrder.total_cost) }}.
            <router-link to="/orders">View submitted orders</router-link>
          </p>
          <button
            class="place-order-btn"
            type="button"
            :disabled="submitting || recommendedItems.length === 0"
            @click="placeOrder"
          >
            {{ submitting ? 'Submitting...' : 'Place Order' }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<script>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

export default {
  name: 'Restocking',
  setup() {
    const loading = ref(true)
    const submitting = ref(false)
    const error = ref(null)
    const submitError = ref(null)
    const forecasts = ref([])
    const inventory = ref([])
    const budget = ref(2000)
    const submittedOrder = ref(null)

    const matchedForecasts = computed(() => {
      const inventoryBySku = new Map(inventory.value.map(item => [item.sku.toLowerCase(), item]))
      const inventoryByName = new Map(
        inventory.value.map(item => [item.name.trim().toLowerCase(), item])
      )

      // Forecast and inventory SKUs differ in the seed data, so match exact names as a fallback.
      return forecasts.value
        .map(forecast => {
          const inventoryItem = inventoryBySku.get(forecast.item_sku.toLowerCase()) ||
            inventoryByName.get(forecast.item_name.trim().toLowerCase())
          if (!inventoryItem) return null

          return {
            forecast,
            inventory: inventoryItem,
            forecastGap: Math.max(0, forecast.forecasted_demand - inventoryItem.quantity_on_hand)
          }
        })
        .filter(item => item && item.forecastGap > 0)
        .sort((a, b) =>
          b.forecast.forecasted_demand - a.forecast.forecasted_demand ||
          a.forecast.item_sku.localeCompare(b.forecast.item_sku)
        )
    })

    const unmatchedForecasts = computed(() => {
      const matchedNames = new Set(
        forecasts.value
          .filter(forecast => inventory.value.some(item =>
            item.sku.toLowerCase() === forecast.item_sku.toLowerCase() ||
            item.name.trim().toLowerCase() === forecast.item_name.trim().toLowerCase()
          ))
          .map(forecast => forecast.item_sku)
      )
      return forecasts.value.filter(forecast => !matchedNames.has(forecast.item_sku))
    })

    const budgetedRecommendations = computed(() => {
      let remainingBudget = budget.value

      // Allocate budget in demand priority order, partially filling a forecast gap when needed.
      return matchedForecasts.value
        .map(item => {
          const affordableQuantity = Math.floor((remainingBudget + 0.000001) / item.inventory.unit_cost)
          const recommendedQuantity = Math.min(item.forecastGap, affordableQuantity)
          remainingBudget = Math.max(0, remainingBudget - recommendedQuantity * item.inventory.unit_cost)
          return { ...item, recommendedQuantity }
        })
    })

    const recommendedItems = computed(() =>
      budgetedRecommendations.value.filter(item => item.recommendedQuantity > 0)
    )

    const recommendedTotal = computed(() =>
      recommendedItems.value.reduce(
        (total, item) => total + item.recommendedQuantity * item.inventory.unit_cost,
        0
      )
    )

    const formatCurrency = value =>
      new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits: 2
      }).format(value)

    const loadData = async () => {
      try {
        loading.value = true
        const [forecastData, inventoryData] = await Promise.all([
          api.getDemandForecasts(),
          api.getInventory()
        ])
        forecasts.value = forecastData
        inventory.value = inventoryData
      } catch (err) {
        error.value = 'Failed to load restocking data: ' + err.message
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      submitError.value = null
      submittedOrder.value = null
      submitting.value = true

      try {
        submittedOrder.value = await api.createRestockingOrder({
          budget: budget.value,
          items: recommendedItems.value.map(item => ({
            item_sku: item.inventory.sku,
            quantity: item.recommendedQuantity
          }))
        })
      } catch (err) {
        submitError.value = err.response?.data?.detail || 'Failed to submit restocking order: ' + err.message
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadData)

    return {
      loading,
      submitting,
      error,
      submitError,
      forecasts,
      budget,
      submittedOrder,
      matchedForecasts,
      budgetedRecommendations,
      unmatchedForecasts,
      recommendedItems,
      recommendedTotal,
      formatCurrency,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card,
.recommendations {
  margin-bottom: 1.5rem;
}

.budget-heading,
.section-heading,
.order-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.budget-heading p,
.section-heading p {
  margin: 0.35rem 0 0;
  color: #64748b;
  font-size: 0.875rem;
}

.budget-value {
  color: #0f172a;
  font-size: 1.5rem;
  font-weight: 700;
  white-space: nowrap;
}

.budget-slider {
  display: block;
  width: 100%;
  margin: 1.25rem 0 0.35rem;
  accent-color: #2563eb;
}

.slider-labels {
  display: flex;
  justify-content: space-between;
  color: #64748b;
  font-size: 0.75rem;
}

.section-heading {
  align-items: flex-start;
  margin-bottom: 1rem;
}

.budget-summary {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.2rem;
  color: #64748b;
  font-size: 0.75rem;
  white-space: nowrap;
}

.budget-summary strong {
  color: #0f172a;
  font-size: 0.875rem;
}

.restocking-table {
  min-width: 850px;
}

.restocking-table th,
.restocking-table td {
  padding: 0.8rem 0.65rem;
  text-align: left;
  white-space: nowrap;
}

.restocking-table th:first-child,
.restocking-table td:first-child {
  white-space: normal;
}

.item-subtitle {
  display: block;
  margin-top: 0.2rem;
  color: #64748b;
  font-size: 0.75rem;
  text-transform: capitalize;
}

.muted { color: #94a3b8; }

.data-note {
  margin: 0.9rem 0 0;
  color: #64748b;
  font-size: 0.8rem;
}

.order-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
  margin-top: 1.25rem;
}

.submit-error,
.submit-success {
  flex: 1 1 100%;
  margin: 0;
  font-size: 0.875rem;
}

.submit-error { color: #b91c1c; }
.submit-success { color: #047857; }
.submit-success a { margin-left: 0.25rem; font-weight: 600; }

.place-order-btn {
  padding: 0.65rem 1.1rem;
  border: 0;
  border-radius: 7px;
  background: #2563eb;
  color: white;
  font: inherit;
  font-weight: 650;
  cursor: pointer;
}

.place-order-btn:hover:not(:disabled) { background: #1d4ed8; }
.place-order-btn:disabled { background: #94a3b8; cursor: not-allowed; }

.empty-state {
  padding: 2rem 1rem;
  color: #64748b;
  text-align: center;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  clip-path: inset(50%);
}

@media (max-width: 640px) {
  .budget-heading,
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .budget-summary { align-items: flex-start; }
}
</style>
